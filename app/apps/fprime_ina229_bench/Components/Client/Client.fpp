module Ina229Te0715 {

  @ Bench client of one Ina229.Manager. The serial shell configures and reads the
  @ sensor through the manager's ports, as a flight application would; the rate
  @ group drives periodic sampling. The raw SPI port bypasses the manager and is
  @ used only for identity and link-integrity tests.
  passive component Client {

    output port configure: Ina229.Configure

    output port read: Ina229.Read

    @ Direct transfers for link diagnostics; never used for measurements
    output port spi: Drv.SpiWriteRead

    @ 100 Hz tick from the rate group
    sync input port run: Svc.Sched

  }

}
