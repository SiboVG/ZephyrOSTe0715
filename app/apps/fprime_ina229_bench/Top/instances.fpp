module Ina229Te0715 {

  module Default {
    constant QUEUE_SIZE = 10
    @ Must equal CONFIG_DYNAMIC_THREAD_STACK_SIZE
    constant STACK_SIZE = 16 * 1024
  }

  @ 100 Hz schedule for periodic sampling (`ina stream`)
  instance rateGroup: Svc.ActiveRateGroup base id 0x10001000 \
    queue size Default.QUEUE_SIZE \
    stack size Default.STACK_SIZE \
    priority 43 \
  {
    phase Fpp.ToCpp.Phases.configObjects """
    Svc::ActiveRateGroup::ContextArray contexts(0U);
    """

    phase Fpp.ToCpp.Phases.configComponents """
    rateGroup.configure(ConfigObjects::Ina229Te0715_rateGroup::contexts);
    """
  }

  @ Dispatches the manager commands sent from the shell (`ina cmd`)
  instance cmdDisp: Svc.CommandDispatcher base id 0x10002000 \
    queue size Default.QUEUE_SIZE \
    stack size Default.STACK_SIZE \
    priority 44

  @ Drives the rate group from a Zephyr kernel timer, every 10 ms
  instance rateDriver: Zephyr.ZephyrRateDriver base id 0x10010000 \
  {
    phase Fpp.ToCpp.Phases.configComponents """
    rateDriver.configure(10);
    """

    phase Fpp.ToCpp.Phases.startTasks """
    rateDriver.start();
    """
  }

  instance zephyrTime: Zephyr.ZephyrTime base id 0x10011000

  @ Prints events on the Zephyr console
  instance textLogger: Svc.PassiveTextLogger base id 0x10012000

  @ Prints telemetry on the Zephyr console
  instance tlmPrinter: TeBench.TlmPrinter base id 0x10013000

  @ Sends shell-built commands to cmdDisp
  instance commander: TeBench.ShellCommander base id 0x10014000

  @ SPI1, INA229 on cs-gpios[0]; clock and mode from Kconfig, changed with `ina spi`
  instance spi: Zephyr.ZephyrSpiDriver base id 0x10020000 \
  {
    phase Fpp.ToCpp.Phases.configComponents """
    TeBench::BenchSpi::configure(spi, state.spiHz, state.spiMode);
    """
  }

  @ The device manager under test
  instance sensor: Ina229.Manager base id 0x10030000

  @ Shell and rate-group access to the manager
  instance client: Ina229Te0715.Client base id 0x10040000

}
