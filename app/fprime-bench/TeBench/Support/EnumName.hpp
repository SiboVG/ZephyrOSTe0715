// SPDX-License-Identifier: Apache-2.0
#ifndef TEBENCH_ENUMNAME_HPP
#define TEBENCH_ENUMNAME_HPP

#include <cstddef>

#include "Fw/Types/String.hpp"

namespace TeBench {

//! The name of an FPP enum value ("OK" rather than toString()'s "OK (0)")
template <typename E>
void enumName(const E& value, char* out, std::size_t size) {
    if (size == 0U) {
        return;
    }
    Fw::String text;
    value.toString(text);
    const char* s = text.toChar();
    std::size_t i = 0U;
    while ((s[i] != '\0') && (s[i] != ' ') && (i + 1U < size)) {
        out[i] = s[i];
        i++;
    }
    out[i] = '\0';
}

}  // namespace TeBench

#endif
