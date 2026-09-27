// SPDX-License-Identifier: Apache-2.0
#ifndef TEBENCH_SHELLCOMMANDER_HPP
#define TEBENCH_SHELLCOMMANDER_HPP

// No Zephyr headers here: they define an EMPTY macro that breaks F Prime headers
// included after them (Os/Queue.hpp), and the generated topology includes this file.
#include "TeBench/ShellCommander/ShellCommanderComponentAc.hpp"

namespace TeBench {

//! Builds one command packet at a time and sends it to the command dispatcher. The
//! caller (the shell thread) serializes the arguments into the buffer that begin()
//! returns, then calls send(). One command is outstanding at a time, and a
//! deployment has at most one instance.
class ShellCommander final : public ShellCommanderComponentBase {
  public:
    explicit ShellCommander(const char* compName);

    //! Start a command packet for this opcode; serialize its arguments into the result.
    Fw::ComBuffer& begin(FwOpcodeType opcode);

    //! Send the packet started with begin() and wait up to timeoutMs for its response.
    //! Returns false when the command could not be sent or no response came in time.
    bool send(U32 timeoutMs, Fw::CmdResponse& response);

  private:
    void cmdStatus_handler(FwIndexType portNum,
                           FwOpcodeType opCode,
                           U32 cmdSeq,
                           const Fw::CmdResponse& response) override;

    Fw::ComBuffer m_packet;
    bool m_headerOk = false;
    U32 m_nextContext = 1U;
    // Guarded by the lock in ShellCommander.cpp: context of the command awaiting its
    // response (0: none), and that response
    U32 m_pending = 0U;
    Fw::CmdResponse m_response;
};

}  // namespace TeBench

#endif
