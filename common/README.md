# shared helpers

Scripts and helpers shared across projects. Each project directory can use
these directly after cloning.

- `secret-sweep.sh` — scan the working tree **and full git history** for
  leaked secrets (API keys, tokens, passwords, private keys) and flag
  private IPs / internal hostnames for review. Run it before flipping the
  repo public:
  `./common/secret-sweep.sh`
