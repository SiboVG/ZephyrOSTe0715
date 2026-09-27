module Ina229Te0715 {

  topology Ina229Te0715 {

    instance client
    instance cmdDisp
    instance commander
    instance rateDriver
    instance rateGroup
    instance sensor
    instance spi
    instance textLogger
    instance tlmPrinter
    instance zephyrTime

    command connections instance cmdDisp
    telemetry connections instance tlmPrinter
    text event connections instance textLogger
    time connections instance zephyrTime

    connections RateGroup {
      rateDriver.CycleOut -> rateGroup.CycleIn
      rateGroup.RateGroupMemberOut[0] -> client.run
    }

    connections Sensor {
      client.configure -> sensor.configure
      client.read -> sensor.read
      sensor.spi -> spi.SpiWriteRead
      client.spi -> spi.SpiWriteRead
    }

    connections Shell {
      commander.cmdOut -> cmdDisp.seqCmdBuff[0]
      cmdDisp.seqCmdStatus[0] -> commander.cmdStatus
    }

  }

}
