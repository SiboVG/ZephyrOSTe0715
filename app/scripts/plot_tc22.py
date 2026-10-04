#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Figures of a TC-22 evidence package (sensor_bench.py adxl355-pl).

Reads results.txt and transcript.log of the package and writes PNG figures to --out:

  phase.png        where in the SYNC period DATA_RDY sets, before and after each restart
  streams.png      frame status, acquisition time and |a| range of every stream
  frames.png       the frames printed in step 6, on the PL time base

Without --capture the package holds summary statistics, not every sample: each stream
is reduced on the board to counts, the acquisition time (min, mean, max) and the |a|
range. A package run with --capture also has every frame of some steps
(capture-tc22-<step>.csv), drawn as:

  samples.png      step 5: acceleration over time and its noise spectrum
  timing.png       step 5: read start and duration after the sync instant, sync spacing
  faults.png       steps 9, 11 and 12: the frames around the clock or pulses stopping
  phase-scan.png   step 13: fresh frames against the read time around the sync instant

  uv run --with matplotlib app/scripts/plot_tc22.py \\
      docs/verification/evidence/<date>-adxl355-pl --out <dir>
"""

import argparse
import csv
import os
import re

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
PERIOD_US = 250.0
COLORS = {'complete': '#2b8a3e', 'stale': '#e67700', 'frozen': '#1c7ed6', 'other': '#868e96'}


def fields(text):
    return dict(token.split('=', 1) for token in text.split() if '=' in token)


def streams(results):
    """(step, label, fields) of every result line that reports a stopped stream"""
    found = []
    for line in results:
        m = re.match(r'(PASS|FAIL)\s+(TC-\d+\.\d+)\s+(.*?): .*ADXL_STREAM_STOPPED (.*)', line)
        if m:
            found.append((m.group(2), m.group(3), fields(m.group(4))))
    return found


def short_label(step, name):
    if step == 'TC-22.8':
        return f'8: delay {re.search(r"interrupt (\d+) us", name).group(1)} us'
    if step == 'TC-22.7':
        return f'7: restart {re.search(r"restart (\d+)", name).group(1)}'
    return {'TC-22.5': '5: 20000 frames', 'TC-22.9': '9: clock stopped\n(timer)',
            'TC-22.10': '10: clock back', 'TC-22.11': '11: clock stopped\nmid-stream (timer)',
            'TC-22.12': '12: pulses stopped\nmid-stream'}.get(step, step)


def phase_figure(transcript, out):
    phases = [fields(l) for l in transcript.splitlines() if l.startswith('ADXL_PHASE ')]
    labels = ['before', 'after restart 1', 'after restart 2', 'after restart 3'][:len(phases)]
    # Relative to the sync instant: phases near the end of the period are just before it
    windows = []
    for f in phases:
        lo, hi = float(f['phase_lo_us']), float(f['phase_hi_us'])
        if lo > PERIOD_US / 2:
            lo, hi = lo - PERIOD_US, hi - PERIOD_US
        windows.append((lo, hi))
    common = (max(w[0] for w in windows), min(w[1] for w in windows))

    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    ax.axvspan(*common, color='#d0ebff', label=f'common window {common[0]:+.1f} to {common[1]:+.1f} µs')
    for i, (lo, hi) in enumerate(windows):
        ax.plot([lo, hi], [i, i], lw=8, solid_capstyle='butt', color='#1c7ed6')
        ax.text(hi + 0.4, i, f'{lo:+.1f} to {hi:+.1f} µs', va='center', fontsize=8)
    ax.axvline(0, color='black', lw=1)
    ax.text(0.3, -0.45, 'sync instant', fontsize=8)
    ax.set_yticks(range(len(windows)), labels)
    ax.set_ylim(-0.6, len(windows) - 0.2)
    ax.invert_yaxis()
    ax.set_xlim(-20, 15)
    ax.set_xlabel('time of DATA_RDY relative to the sync instant (µs)')
    ax.set_title('TC-22 step 7: DATA_RDY phase in the 250 µs SYNC period', fontsize=10)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.22), fontsize=8, frameon=False)
    ax.grid(axis='x', alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'phase.png'), dpi=200)
    plt.close(fig)


def streams_figure(results, out):
    data = streams(results)
    labels = [short_label(step, name) for step, name, _ in data]
    x = range(len(data))
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)

    # Frame status as a share of the frames of each stream
    ax = axes[0]
    bottom = [0.0] * len(data)
    for key in ('complete', 'stale', 'frozen', 'other'):
        values = []
        for _, _, f in data:
            frames = float(f['frames'])
            count = float(f[key]) + (float(f.get('implausible', 0)) + float(f.get('busy', 0)) if key == 'other' else 0)
            values.append(100 * count / frames if frames else 0)
        ax.bar(x, values, bottom=bottom, color=COLORS[key], label=key, width=0.7)
        bottom = [b + v for b, v in zip(bottom, values)]
    for i, (_, _, f) in enumerate(data):
        ax.text(i, 101, f['frames'], ha='center', va='bottom', fontsize=7)
    ax.set_ylim(0, 112)
    ax.set_ylabel('frames (%)')
    ax.set_title('TC-22: every stream (frame count above the bar)', fontsize=10, pad=24)
    ax.legend(ncol=4, fontsize=8, loc='lower center', bbox_to_anchor=(0.5, 1.0), frameon=False)

    # Acquisition time of one frame: min, mean, max
    ax = axes[1]
    for i, (_, _, f) in enumerate(data):
        lo, mean, hi = float(f['acq_min_us']), float(f['acq_mean_us']), float(f['acq_max_us'])
        ax.plot([i, i], [lo, hi], color='#495057', lw=2)
        ax.plot(i, mean, 'o', color='#1c7ed6', ms=5)
        ax.text(i + 0.12, hi, f'{hi:.0f}', fontsize=7, va='center')
    ax.set_ylim(0, 100)
    ax.set_ylabel('acquisition (µs)')
    ax.text(0.99, 0.95, 'line: min to max, dot: mean; the period is 250 µs; SCLK 8.93 MHz, one sensor',
            transform=ax.transAxes, ha='right', va='top', fontsize=8)

    # |a| range over the valid samples
    ax = axes[2]
    for i, (_, _, f) in enumerate(data):
        lo, hi = float(f['mag_min_g']), float(f['mag_max_g'])
        if lo > 0:
            ax.plot([i, i], [lo, hi], color='#2b8a3e', lw=4, solid_capstyle='butt')
            if hi - lo < 1e-5:  # one value: the frozen sample and its repeats
                ax.plot(i, lo, 'D', color='#1c7ed6', ms=5)
                ax.text(i + 0.15, lo, 'one value\n(frozen)', fontsize=7, va='center')
    ax.set_ylabel('|a| of valid samples (g)')
    ax.set_xticks(list(x), labels, rotation=45, ha='right', fontsize=8)
    ax.grid(axis='y', alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'streams.png'), dpi=200)
    plt.close(fig)


def frames_figure(transcript, out):
    rows = []
    for line in transcript.splitlines():
        m = re.match(r'ADXL_FRAME,(\d+),(\d+),0x[0-9a-f]+,(\w+),(-?\d+),(-?\d+),(-?\d+),([-\d.]+),([-\d.]+),([-\d.]+)',
                      line)
        if m:
            rows.append(m.groups())
    if not rows:
        return
    t0 = int(rows[0][1])
    t = [(int(r[1]) - t0) / 1000 for r in rows]
    fig, axes = plt.subplots(2, 1, figsize=(7.5, 5), sharex=True)
    for col, name, color in ((6, 'x', '#c92a2a'), (7, 'y', '#2b8a3e'), (8, 'z', '#1c7ed6')):
        values = [float(r[col]) for r in rows]
        mean = sum(values) / len(values)
        axes[0].plot(t, [1000 * (v - mean) for v in values], 'o-', color=color, ms=4,
                     label=f'{name} (mean {mean:+.4f} g)')
    axes[0].set_ylabel('deviation from mean (mg)')
    axes[0].legend(fontsize=8, ncol=3)
    axes[0].set_title(f'TC-22 step 6: the {len(rows)} printed frames (the console skips the frames between)',
                      fontsize=10)
    steps = [(int(b[1]) - int(a[1])) / PERIOD_US for a, b in zip(rows, rows[1:])]
    axes[1].bar(t[1:], steps, width=1.5, color='#495057')
    for ti, s in zip(t[1:], steps):
        axes[1].text(ti, s + 0.3, f'{s:g}', ha='center', fontsize=7)
    axes[1].set_ylim(0, max(steps) + 4)
    axes[1].set_ylabel('sync periods since\nthe previous frame')
    axes[1].set_xlabel('sync time on the PL time base, from the first printed frame (ms)')
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'frames.png'), dpi=200)
    plt.close(fig)


STATUS_NAMES = {0: 'OK', 13: 'STALE_DATA', 14: 'IMPLAUSIBLE_DATA', 16: 'FROZEN_DATA', 12: 'BUSY'}
STATUS_COLORS = {0: COLORS['complete'], 13: COLORS['stale'], 16: COLORS['frozen']}
LSB_PER_G = 256000.0  # +/-2 g, typical (TC-22 initializes at +/-2 g)


def load_capture(path):
    """The frames of a capture-tc22-<step>.csv as a dict of numpy arrays"""
    import numpy as np
    with open(path) as f:
        rows = list(csv.DictReader(f))
    keys = ['index', 'stream', 'sequence', 'sync_us', 'sync_ticks', 'start_ns', 'end_ns', 'status', 'valid',
            'raw_x', 'raw_y', 'raw_z']
    return {k: np.array([int(r[k]) for r in rows], dtype=np.int64) for k in keys}


def welch(x, fs, segment):
    """One-sided power spectral density by Welch's method (Hann window, half overlap)"""
    import numpy as np
    window = np.hanning(segment)
    scale = 1.0 / (fs * (window ** 2).sum())
    spectra = []
    for start in range(0, len(x) - segment + 1, segment // 2):
        part = x[start:start + segment]
        part = (part - part.mean()) * window
        spectra.append(np.abs(np.fft.rfft(part)) ** 2 * scale)
    psd = np.mean(spectra, axis=0)
    psd[1:-1] *= 2
    return np.fft.rfftfreq(segment, 1 / fs), psd


def samples_figure(cap, out):
    import numpy as np
    ok = cap['status'] == 0
    t = (cap['sync_ticks'][ok] - cap['sync_ticks'][ok][0]) / 128e6
    fig, axes = plt.subplots(2, 1, figsize=(10, 7))
    ax = axes[0]
    for key, name, color in (('raw_x', 'x', '#c92a2a'), ('raw_y', 'y', '#2b8a3e'), ('raw_z', 'z', '#1c7ed6')):
        g = cap[key][ok] / LSB_PER_G
        ax.plot(t, 1000 * (g - g.mean()), lw=0.4, color=color, alpha=0.8,
                label=f'{name}: mean {g.mean():+.5f} g, rms {1000 * g.std():.3f} mg')
    ax.set_xlabel('time on the PL time base (s)')
    ax.set_ylabel('deviation from mean (mg)')
    ax.set_title(f'TC-22 step 5: {ok.sum()} samples at 4 kHz, sensor at rest', fontsize=10)
    ax.legend(fontsize=8, ncol=3, loc='upper right')
    ax = axes[1]
    for key, name, color in (('raw_x', 'x', '#c92a2a'), ('raw_y', 'y', '#2b8a3e'), ('raw_z', 'z', '#1c7ed6')):
        g = cap[key][ok] / LSB_PER_G
        f, psd = welch(g, 4000.0, 2048)
        density = 1e6 * np.sqrt(psd)  # micro-g per root hertz
        band = (f > 10) & (f < 500)
        ax.loglog(f[1:], density[1:], lw=0.8, color=color,
                  label=f'{name}: median {np.median(density[band]):.1f} µg/√Hz (10 to 500 Hz)')
    ax.set_xlabel('frequency (Hz)')
    ax.set_ylabel('noise density (µg/√Hz)')
    ax.set_xlim(1, 2000)
    ax.grid(which='both', alpha=0.3)
    ax.legend(fontsize=8)
    ax.set_title('Noise spectrum (Welch, 2048-sample Hann segments); the 4 kHz output filter rolls off near 1 kHz',
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'samples.png'), dpi=200)
    plt.close(fig)


def timing_figure(cap, out):
    import numpy as np
    start = cap['start_ns'] / 1000
    duration = (cap['end_ns'] - cap['start_ns']) / 1000
    spacing = np.diff(cap['sync_ticks'])
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6))
    ax = axes[0]
    ax.hist(start, bins=100, color='#1c7ed6')
    ax.set_xlabel('read start after the sync instant (µs)')
    ax.set_ylabel('frames')
    ax.set_title(f'IRQ_DELAY plus latency\nmin {start.min():.2f}, median {np.median(start):.2f}, '
                 f'max {start.max():.2f} µs', fontsize=9)
    ax = axes[1]
    ax.hist(duration, bins=100, color='#495057')
    ax.set_xlabel('acquisition, start to end (µs)')
    ax.set_title(f'one sensor, SCLK 8.93 MHz\nmin {duration.min():.2f}, median {np.median(duration):.2f}, '
                 f'max {duration.max():.2f} µs', fontsize=9)
    ax = axes[2]
    values, counts = np.unique(spacing, return_counts=True)
    ax.bar([str(v) for v in values], counts, color='#2b8a3e')
    ax.set_xlabel('sync instant spacing (time base ticks)')
    ax.set_title(f'{len(spacing)} intervals; 32000 ticks = 250 µs', fontsize=9)
    for i, c in enumerate(counts):
        ax.text(i, c, str(c), ha='center', va='bottom', fontsize=8)
    ax.set_ylim(0, counts.max() * 1.15)
    fig.suptitle('TC-22 step 5: timing of every frame on the PL time base', fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'timing.png'), dpi=200)
    plt.close(fig)


def status_strip(ax, index, status, title):
    for code in sorted(set(int(c) for c in status)):
        sel = status == code
        ax.scatter(index[sel], [0] * int(sel.sum()), marker='|', s=200,
                   color=STATUS_COLORS.get(code, COLORS['other']), label=STATUS_NAMES.get(code, str(code)))
    ax.set_yticks([])
    ax.set_title(title, fontsize=9)
    ax.legend(fontsize=7, loc='upper right', ncol=3)


def faults_figure(captures, out):
    import numpy as np
    panels = [step for step in ('9', '11', '12') if step in captures]
    fig, axes = plt.subplots(len(panels), 2, figsize=(12, 2.8 * len(panels)), squeeze=False)
    for row, step in enumerate(panels):
        cap = captures[step]
        n = np.arange(len(cap['index']))
        bad = np.flatnonzero(cap['status'] != 0)
        if step == '12':
            # The pulses stop: the frames end; their sync instants stay 250 us apart
            t = (cap['sync_ticks'] - cap['sync_ticks'][0]) / 128e3
            status_strip(axes[row][0], t, cap['status'], f'step 12: {len(n)} PL-triggered frames, pulses '
                         f'stopped; last frame at {t[-1]:.1f} ms')
            axes[row][0].set_xlabel('sync instant (ms)')
            gaps = np.diff(cap['sync_ticks'])
            axes[row][1].plot(t[1:], gaps / 128, '.', ms=2, color='#495057')
            axes[row][1].set_ylabel('spacing (µs)')
            axes[row][1].set_xlabel('sync instant (ms)')
            regular = int((gaps == 32000).sum())
            axes[row][1].set_title(f'{regular} of {len(gaps)} frames 250 µs after the frame before', fontsize=9)
            continue
        first_bad = int(bad[0]) if len(bad) else len(n)
        lo, hi = max(first_bad - 20, 0), min(first_bad + 20, len(n))
        status_strip(axes[row][0], n, cap['status'],
                     f'step {step}: {len(n)} timer-triggered frames; first invalid frame {first_bad}')
        axes[row][0].set_xlabel('frame')
        ax = axes[row][1]
        x = cap['raw_x'][lo:hi]
        ok = cap['status'][lo:hi] == 0
        ax.plot(n[lo:hi][ok], x[ok] / LSB_PER_G * 1000, 'o', ms=3, color=COLORS['complete'], label='valid sample')
        ax.axvline(first_bad - 0.5, color='black', lw=0.8)
        ax.set_xlabel('frame')
        ax.set_ylabel('x of valid samples (mg)')
        ax.set_title('around the first invalid frame (line); frozen repeats show as a flat run', fontsize=9)
        ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'faults.png'), dpi=200)
    plt.close(fig)


def phase_scan_figure(cap, transcript, out):
    import numpy as np
    # Read start relative to the next sync instant, the one whose sample it can see
    t = cap['start_ns'] / 1000 - PERIOD_US
    fresh = cap['status'] == 0
    edges = np.arange(np.floor(t.min()), np.ceil(t.max()) + 0.5, 0.5)
    which = np.digitize(t, edges)
    centers, share, counts = [], [], []
    for b in range(1, len(edges)):
        sel = which == b
        if sel.sum() >= 5:
            centers.append((edges[b - 1] + edges[b]) / 2)
            share.append(fresh[sel].mean())
            counts.append(int(sel.sum()))
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.plot(centers, share, 'o-', ms=3, color='#1c7ed6', label='share of fresh frames (0.5 µs bins)')
    phases = [fields(l) for l in transcript.splitlines() if l.startswith('ADXL_PHASE ')]
    if phases:
        lo = max(float(f['phase_lo_us']) for f in phases) - PERIOD_US
        hi = min(float(f['phase_hi_us']) for f in phases) - PERIOD_US
        ax.axvspan(lo, hi, color='#d0ebff', label=f'step 7 window {lo:+.1f} to {hi:+.1f} µs')
    crossing = next((c for c, s in zip(centers, share) if s >= 0.5), None)
    if crossing is not None:
        ax.axvline(crossing, color='black', lw=0.8)
        ax.text(crossing + 0.3, 0.1, f'half fresh at {crossing:+.2f} µs', fontsize=8)
    ax.set_xlabel('read start relative to the sync instant (µs)')
    ax.set_ylabel('fresh frames')
    ax.set_ylim(-0.05, 1.05)
    ax.set_title(f'TC-22 step 13: {len(t)} frames read around the sync instant; the read start is a few µs '
                 'before the STATUS byte', fontsize=9)
    ax.legend(fontsize=8, loc='center right')
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out, 'phase-scan.png'), dpi=200)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('package', help='TC-22 evidence directory')
    parser.add_argument('--out', required=True, help='directory for the figures (created)')
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.package, 'results.txt')) as f:
        results = f.read().splitlines()
    with open(os.path.join(args.package, 'transcript.log'), 'rb') as f:
        transcript = ANSI.sub('', f.read().decode(errors='replace')).replace('\r', '')
    # A result line can be glued to an echoed prompt; the frames are taken as
    # sensor_bench.py takes them (whole lines only), so the counts match results.txt
    transcript = re.sub(r'(?<!\n)(ADXL_PHASE )', r'\n\1', transcript)
    phase_figure(transcript, args.out)
    streams_figure(results, args.out)
    frames_figure(transcript, args.out)
    captures = {}
    for step in ('5', '9', '11', '12', '13'):
        path = os.path.join(args.package, f'capture-tc22-{step}.csv')
        if os.path.exists(path):
            captures[step] = load_capture(path)
    if '5' in captures:
        samples_figure(captures['5'], args.out)
        timing_figure(captures['5'], args.out)
    if any(step in captures for step in ('9', '11', '12')):
        faults_figure(captures, args.out)
    if '13' in captures:
        phase_scan_figure(captures['13'], transcript, args.out)
    print('\n'.join(sorted(os.path.join(args.out, n) for n in os.listdir(args.out) if n.endswith('.png'))))


if __name__ == '__main__':
    main()
