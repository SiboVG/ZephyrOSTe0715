module CspBenchZephyr {

  module Default {
    constant QUEUE_SIZE = 10
    @ Must equal CONFIG_DYNAMIC_THREAD_STACK_SIZE
    constant STACK_SIZE = 16 * 1024
  }

  @ 1 Hz schedule, as in the Linux CspBench deployment
  instance rateGroup_1Hz: Svc.ActiveRateGroup base id 0x10001000 \
    queue size Default.QUEUE_SIZE \
    stack size Default.STACK_SIZE \
    priority 43 \
  {
    phase Fpp.ToCpp.Phases.configObjects """
    Svc::ActiveRateGroup::ContextArray contexts(0U);
    """

    phase Fpp.ToCpp.Phases.configComponents """
    rateGroup_1Hz.configure(ConfigObjects::CspBenchZephyr_rateGroup_1Hz::contexts);
    """
  }

  @ Owns the libcsp stack and the libparam server
  instance cspLibparam: CubeSpec.CspLibparam base id 0x10002000 \
    queue size Default.QUEUE_SIZE \
    stack size Default.STACK_SIZE \
    priority 42 \
  {
    phase Fpp.ToCpp.Phases.configComponents """
    const bool configured = cspLibparam.configure(state.config);
    state.startupOk = configured && state.startupOk;
    """

    phase Fpp.ToCpp.Phases.startTasks """
    cspLibparam.start(
        static_cast<FwTaskPriorityType>(Priorities::CspBenchZephyr_cspLibparam),
        static_cast<Os::Task::ParamType>(StackSizes::CspBenchZephyr_cspLibparam),
        Os::Task::TASK_DEFAULT,
        static_cast<Os::Task::ParamType>(TaskIds::CspBenchZephyr_cspLibparam)
    );
    if (state.startupOk) {
        state.startupOk = cspLibparam.startRuntime();
    }
    """
  }

  @ Drives the rate group from a Zephyr kernel timer
  instance rateDriver: Zephyr.ZephyrRateDriver base id 0x10010000 \
  {
    phase Fpp.ToCpp.Phases.configComponents """
    rateDriver.configure(1000);
    """

    phase Fpp.ToCpp.Phases.startTasks """
    rateDriver.start();
    """
  }

  instance zephyrTime: Zephyr.ZephyrTime base id 0x10011000

  @ Registers the component commands (required by the generated topology)
  instance cmdDisp: Svc.CommandDispatcher base id 0x10013000 \
    queue size Default.QUEUE_SIZE \
    stack size Default.STACK_SIZE \
    priority 44

  @ Prints events on the Zephyr console
  instance textLogger: Svc.PassiveTextLogger base id 0x10012000

}
