// SPDX-License-Identifier: Apache-2.0
#include "TeBench/TlmPrinter/TlmPrinter.hpp"

#include <zephyr/sys/printk.h>

namespace TeBench {

TlmPrinter::TlmPrinter(const char* compName) : TlmPrinterComponentBase(compName) {}

bool TlmPrinter::add(FwChanIdType id, const char* name, Formatter formatter) {
    if ((this->m_count >= MAX_CHANNELS) || (name == nullptr) || (formatter == nullptr)) {
        return false;
    }
    this->m_entries[this->m_count++] = Entry{id, name, formatter};
    return true;
}

bool TlmPrinter::formatF64(Fw::TlmBuffer& value, char* text, FwSizeType size) {
    F64 v = 0.0;
    if (value.deserializeTo(v) != Fw::FW_SERIALIZE_OK) {
        return false;
    }
    (void)snprintf(text, size, "%.9g", v);
    return true;
}

void TlmPrinter::tlmIn_overflowHook(FwIndexType portNum, FwChanIdType id, Fw::Time& timeTag, Fw::TlmBuffer& val) {
    (void)portNum;
    (void)id;
    (void)timeTag;
    (void)val;
    this->m_dropped.fetch_add(1U);
}

void TlmPrinter::tlmIn_handler(FwIndexType portNum, FwChanIdType id, Fw::Time& timeTag, Fw::TlmBuffer& val) {
    (void)portNum;
    for (FwSizeType i = 0; i < this->m_count; i++) {
        const Entry& entry = this->m_entries[i];
        if (entry.id != id) {
            continue;
        }
        char text[160];
        val.resetDeser();
        if (!entry.formatter(val, text, sizeof(text))) {
            break;
        }
        if (this->m_enabled.load()) {
            printk("TLM %s = %s (%" PRIu32 ".%06" PRIu32 ")\n", entry.name, text, timeTag.getSeconds(),
                   timeTag.getUSeconds());
        }
        return;
    }
    this->m_unprinted.fetch_add(1U);
}

}  // namespace TeBench
