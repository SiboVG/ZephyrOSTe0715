// SPDX-License-Identifier: Apache-2.0
#ifndef TEBENCH_TLMPRINTER_HPP
#define TEBENCH_TLMPRINTER_HPP

#include <atomic>
#include <cinttypes>
#include <cstdio>

#include "Fw/Types/String.hpp"
#include "TeBench/TlmPrinter/TlmPrinterComponentAc.hpp"

namespace TeBench {

class TlmPrinter final : public TlmPrinterComponentBase {
  public:
    //! Decodes one serialized value into text; returns false if it does not decode.
    using Formatter = bool (*)(Fw::TlmBuffer& value, char* text, FwSizeType size);

    explicit TlmPrinter(const char* compName);

    //! Register a channel during setup, before any telemetry is written. Returns false
    //! when the table is full.
    bool add(FwChanIdType id, const char* name, Formatter formatter);

    void setEnabled(bool enabled) { this->m_enabled.store(enabled); }
    bool isEnabled() const { return this->m_enabled.load(); }

    //! Values written to unregistered channels, or that did not decode (not printed)
    U32 unprintedCount() const { return this->m_unprinted.load(); }

    //! Values dropped because the queue was full
    U32 droppedCount() const { return this->m_dropped.load(); }

    template <typename T>
    static bool formatUnsigned(Fw::TlmBuffer& value, char* text, FwSizeType size) {
        T v = 0;
        if (value.deserializeTo(v) != Fw::FW_SERIALIZE_OK) {
            return false;
        }
        (void)snprintf(text, size, "%" PRIu64, static_cast<uint64_t>(v));
        return true;
    }

    template <typename T>
    static bool formatSigned(Fw::TlmBuffer& value, char* text, FwSizeType size) {
        T v = 0;
        if (value.deserializeTo(v) != Fw::FW_SERIALIZE_OK) {
            return false;
        }
        (void)snprintf(text, size, "%" PRId64, static_cast<int64_t>(v));
        return true;
    }

    static bool formatF64(Fw::TlmBuffer& value, char* text, FwSizeType size);

    //! For generated FPP enums and small structs: their toString() text
    template <typename T>
    static bool formatSerializable(Fw::TlmBuffer& value, char* text, FwSizeType size) {
        T v;
        if (v.deserializeFrom(value) != Fw::FW_SERIALIZE_OK) {
            return false;
        }
        Fw::String s;
        v.toString(s);
        (void)snprintf(text, size, "%s", s.toChar());
        return true;
    }

  private:
    void tlmIn_handler(FwIndexType portNum, FwChanIdType id, Fw::Time& timeTag, Fw::TlmBuffer& val) override;
    void tlmIn_overflowHook(FwIndexType portNum, FwChanIdType id, Fw::Time& timeTag, Fw::TlmBuffer& val) override;

    struct Entry {
        FwChanIdType id;
        const char* name;
        Formatter formatter;
    };
    static constexpr FwSizeType MAX_CHANNELS = 48;
    Entry m_entries[MAX_CHANNELS] = {};
    FwSizeType m_count = 0;
    std::atomic<bool> m_enabled{true};
    std::atomic<U32> m_unprinted{0U};
    std::atomic<U32> m_dropped{0U};
};

}  // namespace TeBench

#endif
