module TeBench {

  @ Prints telemetry on the console when it is written, as "TLM <channel> = <value>",
  @ decoded by the formatter the deployment registers for each channel. The benches
  @ have no ground link, so this is how the operator and the host scripts see
  @ telemetry. Unregistered channels (such as a rate group's per-cycle RgMaxTime) are
  @ counted, not printed. Printing runs on this component's own thread: a caller,
  @ such as the ADXL355 frame timing thread, never waits for the console.
  active component TlmPrinter {

    @ Values that arrive while the queue is full are dropped and counted
    async input port tlmIn: Fw.Tlm hook

  }

}
