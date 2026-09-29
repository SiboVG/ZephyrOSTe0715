module Adxl355Te0715 {

  module Default {
    constant QUEUE_SIZE = 10
    @ Console printers: room for a burst of throttled events or telemetry
    constant LOG_QUEUE_SIZE = 64
    @ Console printers at the shell's priority (Zephyr 99), see prj.conf
    constant CONSOLE_PRIORITY = 0
    @ Must equal CONFIG_DYNAMIC_THREAD_STACK_SIZE
    constant STACK_SIZE = 16 * 1024
  }

  @ 10 Hz schedule: publishes the manager's and the application's fault edges
  @ (their schedIn ports), below the frame timing thread's priority
  instance rateGroup: Svc.ActiveRateGroup base id 0x10001000 \
    queue size Default.QUEUE_SIZE \
    stack size Default.STACK_SIZE \
    priority 43 \
  {
    phase Fpp.ToCpp.Phases.configObjects """
    Svc::ActiveRateGroup::ContextArray contexts(0U);
    """

    phase Fpp.ToCpp.Phases.configComponents """
    rateGroup.configure(ConfigObjects::Adxl355Te0715_rateGroup::contexts);
    """
  }

  @ Drives the rate group from a Zephyr kernel timer, every 100 ms
  instance rateDriver: Zephyr.ZephyrRateDriver base id 0x10010000 \
  {
    phase Fpp.ToCpp.Phases.configComponents """
    rateDriver.configure(100);
    """

    phase Fpp.ToCpp.Phases.startTasks """
    rateDriver.start();
    """
  }

  @ Dispatches the manager and application commands sent from the shell (`adxl cmd`)
  instance cmdDisp: Svc.CommandDispatcher base id 0x10002000 \
    queue size Default.QUEUE_SIZE \
    stack size Default.STACK_SIZE \
    priority 44

  instance zephyrTime: Zephyr.ZephyrTime base id 0x10011000

  @ Prints events on the Zephyr console, from its own thread, so that emitting an
  @ event never waits for the 115200 baud console
  instance textLogger: Svc.ActiveTextLogger base id 0x10012000 \
    queue size Default.LOG_QUEUE_SIZE \
    stack size Default.STACK_SIZE \
    priority Default.CONSOLE_PRIORITY

  @ Prints telemetry on the Zephyr console, also from its own thread
  instance tlmPrinter: TeBench.TlmPrinter base id 0x10013000 \
    queue size Default.LOG_QUEUE_SIZE \
    stack size Default.STACK_SIZE \
    priority Default.CONSOLE_PRIORITY

  @ Sends shell-built commands to cmdDisp
  instance commander: TeBench.ShellCommander base id 0x10014000

  @ SPI1, ADXL355 on the chip select SS0; clock and mode from Kconfig, changed with `adxl spi`
  instance spi: Zephyr.ZephyrSpiDriver base id 0x10020000 \
  {
    phase Fpp.ToCpp.Phases.configComponents """
    TeBench::BenchSpi::configure(spi, state.spiHz, state.spiMode);
    """
  }

  @ The device manager under test
  instance sensor: Adxl355.Manager base id 0x10030000

  @ The synchronized application under test, with one sensor
  instance app: Adxl355.SynchronizedApplication base id 0x10031000 \
  {
    phase Fpp.ToCpp.Phases.configComponents """
    state.appConfigured = (app.configure(1U) == Adxl355::DriverStatus::OK);
    """
  }

  @ Shell and timing-thread access to the manager and the application
  instance client: Adxl355Te0715.Client base id 0x10040000

}
