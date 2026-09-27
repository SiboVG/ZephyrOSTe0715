module Adxl355Te0715 {

  topology Adxl355Te0715 {

    instance app
    instance client
    instance cmdDisp
    instance commander
    instance sensor
    instance spi
    instance textLogger
    instance tlmPrinter
    instance zephyrTime

    command connections instance cmdDisp
    telemetry connections instance tlmPrinter
    text event connections instance textLogger
    time connections instance zephyrTime

    connections Application {
      client.acquireFrame -> app.acquireFrame
      app.configureSensor[0] -> sensor.configure
      app.readSensor[0] -> sensor.readAcceleration
      app.frameReady -> client.frameReady
    }

    connections Sensor {
      client.configure -> sensor.configure
      client.readAcceleration -> sensor.readAcceleration
      client.readTemperature -> sensor.readTemperature
      client.measurementControl -> sensor.measurementControl
      sensor.spi -> spi.SpiWriteRead
      client.spi -> spi.SpiWriteRead
    }

    connections Shell {
      commander.cmdOut -> cmdDisp.seqCmdBuff[0]
      cmdDisp.seqCmdStatus[0] -> commander.cmdStatus
    }

  }

}
