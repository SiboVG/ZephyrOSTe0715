module CspBenchZephyr {

  topology CspBenchZephyr {

    instance cmdDisp
    instance cspLibparam
    instance rateDriver
    instance rateGroup_1Hz
    instance textLogger
    instance zephyrTime

    command connections instance cmdDisp
    time connections instance zephyrTime
    text event connections instance textLogger

    connections RateGroup {
      rateDriver.CycleOut -> rateGroup_1Hz.CycleIn
      rateGroup_1Hz.RateGroupMemberOut[0] -> cspLibparam.run
    }

  }

}
