// SPDX-License-Identifier: Apache-2.0
#include "TeBench/ShellCommander/ShellCommander.hpp"

#include "Fw/Com/ComPacket.hpp"
#include "Fw/Types/Assert.hpp"

#include <zephyr/kernel.h>

namespace TeBench {

namespace {
// State shared by the shell thread (send) and the dispatcher thread (cmdStatus); one
// instance per deployment
K_SEM_DEFINE(g_done, 0, 1);
struct k_spinlock g_lock;
bool g_constructed = false;
}  // namespace

ShellCommander::ShellCommander(const char* compName) : ShellCommanderComponentBase(compName) {
    FW_ASSERT(!g_constructed);
    g_constructed = true;
}

Fw::ComBuffer& ShellCommander::begin(FwOpcodeType opcode) {
    this->m_packet.resetSer();
    // The dispatcher expects the packet type, the opcode, then the arguments
    // (Fw::CmdPacket::deserializeFrom)
    this->m_headerOk =
        (this->m_packet.serializeFrom(static_cast<FwPacketDescriptorType>(Fw::ComPacketType::FW_PACKET_COMMAND)) ==
         Fw::FW_SERIALIZE_OK) &&
        (this->m_packet.serializeFrom(opcode) == Fw::FW_SERIALIZE_OK);
    return this->m_packet;
}

bool ShellCommander::send(U32 timeoutMs, Fw::CmdResponse& response) {
    if (!this->m_headerOk || !this->isConnected_cmdOut_OutputPort(0)) {
        return false;
    }
    U32 context = this->m_nextContext++;
    if (context == 0U) {
        context = this->m_nextContext++;
    }

    k_sem_reset(&g_done);
    k_spinlock_key_t key = k_spin_lock(&g_lock);
    this->m_pending = context;
    k_spin_unlock(&g_lock, key);

    this->cmdOut_out(0, this->m_packet, context);
    const bool answered = k_sem_take(&g_done, K_MSEC(timeoutMs)) == 0;

    key = k_spin_lock(&g_lock);
    // A late response for this context is dropped by the handler from now on
    this->m_pending = 0U;
    if (answered) {
        response = this->m_response;
    }
    k_spin_unlock(&g_lock, key);
    return answered;
}

void ShellCommander::cmdStatus_handler(FwIndexType portNum,
                                       FwOpcodeType opCode,
                                       U32 cmdSeq,
                                       const Fw::CmdResponse& response) {
    (void)portNum;
    (void)opCode;
    bool matched = false;
    k_spinlock_key_t key = k_spin_lock(&g_lock);
    if ((this->m_pending != 0U) && (cmdSeq == this->m_pending)) {
        this->m_response = response;
        this->m_pending = 0U;
        matched = true;
    }
    k_spin_unlock(&g_lock, key);
    if (matched) {
        k_sem_give(&g_done);
    }
}

}  // namespace TeBench
