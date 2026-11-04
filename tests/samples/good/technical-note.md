# Cache layer notes

This is the way the parser walks a config file: it reads one line, finds the key, and hands the value to the cache.

The cache is fast, simple, and reliable because it does one thing. Most developers use Git to track changes like this, so the history lives next to the code.

Don’t wait for the lock if the read is read-only. Call `get_nowait()` and move on.

The estimator is robust to outliers, which matters when one request takes 40 seconds. The staging app works like a prototype of the full site, and the tests cover the rest.

The scheduler has two modes, BATCH and JUST IN time, and we run the second. Setup steps for a new machine -> linked from the README.

```sh
leverage --seamless --quietly   # flag names from the old tool
```

The full config is in `cache.toml`.
