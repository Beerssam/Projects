#!/usr/bin/env python3
"""dmrgateway-rptl-passthrough.py -- replace DMRGateway::getConfig() with an
MMDVM RPTC passthrough (Oct 19-20 2026 BrandMeister fix).

Problem: DMRGateway rebuilds the RPTC config message by hand in getConfig().
It reads the tail fields (flags byte, software name/version, package ID) from
wrong offsets of the captured MMDVM config, so BrandMeister receives a mangled
RPTC and rejects the login ~50ms after the RPTC ("Login to the master has
failed"). TGIF and KS-DMR never inspect those fields, so they worked.

Evidence (node, 2026-10-19): MMDVM_Bridge connected DIRECTLY to BM sent its
own 294-byte RPTC and BM verified it. The direct-connection bytes are
byte-identical to what MMDVM_Bridge hands DMRGateway via the local RPTC
packet, so the fix is to stop rebuilding and pass those bytes through
verbatim. Live node log 2026-10-20 ~01:20 UTC confirmed the passthrough RPTC
carries the real software "20210520_V1.6.8" / package "MMDVM_DMO" fields and
no "Login to the master has failed" followed.

Why python instead of a unified diff: the getConfig() body is long and the
exact tab/space rendering varies between checkouts; brace-matching on the
function signature is deterministic at the pinned stable commit 29397cf.

Usage: python3 dmrgateway-rptl-passthrough.py [path/to/DMRGateway.cpp]
Idempotent: exits 0 without changes if already applied.
"""
import sys

MARKER = "// RPTL/DVSwitch fix: pass the MMDVM's captured RPTC payload through verbatim."
SIG = "unsigned int CDMRGateway::getConfig(const std::string& name, unsigned char* buffer)"

NEW_FUNC = """unsigned int CDMRGateway::getConfig(const std::string& name, unsigned char* buffer)
{
\tassert(buffer != NULL);

\t// RPTL/DVSwitch fix: pass the MMDVM's captured RPTC payload through verbatim.
\t// Rebuilding it here mis-parses the MMDVM_Bridge field layout (tail fields
\t// read from wrong offsets), and BrandMeister rejects the login ~50ms after
\t// the RPTC. This payload is byte-identical to what MMDVM_Bridge sends when
\t// connected directly, which BM accepts (verified 2026-10-19).
\tunsigned int len = m_repeater->getShortConfig(buffer);
\tif (len == 0U) {
\t\tLogError("%s, no MMDVM config captured, cannot build RPTC", name.c_str());
\t\treturn 0U;
\t}
\tbuffer[len] = 0U;

\tm_callsign = std::string((char*)m_config + 0U, 8U);
\tsize_t n = m_callsign.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789");
\tif (n != std::string::npos)
\t\tm_callsign.erase(n);
\tchar frequency[10U];
\t::memset(frequency, 0x00U, 10U);
\t::memcpy(frequency, m_config + 8U, 9U);
\tm_rxFrequency = (unsigned int)::atoi(frequency);
\t::memset(frequency, 0x00U, 10U);
\t::memcpy(frequency, m_config + 17U, 9U);
\tm_txFrequency = (unsigned int)::atoi(frequency);

\tLogInfo("%s: configuration message (MMDVM passthrough, %u bytes): %s", name.c_str(), len, buffer);
\treturn len;
}
"""


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "DMRGateway.cpp"
    with open(path) as f:
        s = f.read()
    if MARKER in s:
        print("passthrough already applied, skipping")
        return 0
    start = s.find(SIG)
    if start < 0:
        print("ERROR: getConfig signature not found in %s" % path)
        return 1
    i = s.index("{", start)
    depth = 0
    j = i
    while True:
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    end = j + 1
    s = s[:start] + NEW_FUNC + s[end:]
    with open(path, "w") as f:
        f.write(s)
    print("getConfig replaced with MMDVM passthrough OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
