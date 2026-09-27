module Adxl355Te0715 {

  @ Bench client of one Adxl355.Manager and the Adxl355.SynchronizedApplication. The
  @ serial shell configures and reads the sensor through the manager's ports, as a
  @ flight application would. The bench's timing thread calls acquire(), which drives
  @ the application's acquireFrame port in place of the FPGA synchronization source,
  @ and this client receives and counts the frames. The raw SPI port bypasses the
  @ manager and is used only for identity and link-integrity tests.
  passive component Client {

    output port configure: Adxl355.Configure

    output port readAcceleration: Adxl355.ReadAcceleration

    output port readTemperature: Adxl355.ReadTemperature

    output port measurementControl: Adxl355.MeasurementControl

    @ Direct transfers for link diagnostics; never used for measurements
    output port spi: Drv.SpiWriteRead

    @ Frame trigger to the synchronized application
    output port acquireFrame: Adxl355.AcquireFrame

    @ Frames from the synchronized application
    sync input port frameReady: Adxl355.FrameReady

  }

}
