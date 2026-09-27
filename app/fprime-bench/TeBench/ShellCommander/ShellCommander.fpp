module TeBench {

  @ Sends F Prime commands built by the serial shell to the command dispatcher and
  @ waits for each response, so a shell command exercises the same path as a ground
  @ command. Connect cmdOut to CommandDispatcher.seqCmdBuff[i] and
  @ CommandDispatcher.seqCmdStatus[i] to cmdStatus.
  passive component ShellCommander {

    @ Command packets to the dispatcher
    output port cmdOut: Fw.Com

    @ Responses from the dispatcher; the call context identifies the command
    sync input port cmdStatus: Fw.CmdResponse

  }

}
