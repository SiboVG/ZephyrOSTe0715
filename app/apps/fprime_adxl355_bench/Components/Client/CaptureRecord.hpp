// SPDX-License-Identifier: Apache-2.0
#ifndef ADXL355TE0715_CAPTURE_RECORD_HPP
#define ADXL355TE0715_CAPTURE_RECORD_HPP

#include <Fw/FPrimeBasicTypes.hpp>

namespace Adxl355Te0715 {

//! One frame of a stream as `adxl capture` stores it. The timing thread fills the
//! times, the Client's frameReady handler the frame. Written by the timing thread
//! only, read by `adxl capture dump` once no stream runs.
struct CaptureRecord {
    U64 syncUs;     //!< frame time passed to acquireFrame
    U64 syncTicks;  //!< PL source: the sync instant on the PL time base; timer source: 0
    U32 sequence;   //!< frame sequence number (low 32 bits)
    U32 startNs;    //!< acquisition start after the sync instant (PL) or the timer expiry
    U32 endNs;      //!< acquisition end, likewise
    I32 rawX;
    I32 rawY;
    I32 rawZ;
    U16 stream;     //!< number of the stream since the capture was armed
    U8 status;      //!< DriverStatus of sensor 0
    U8 validMask;
};

}  // namespace Adxl355Te0715

#endif
