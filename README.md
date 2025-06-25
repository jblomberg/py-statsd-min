# py-statsd-min

A minimal Python implementation of Etsy's [statsD].

## Motivations

* [py-statsd] doesn't handle namespaces the way I wanted, and includes a fair
  amount of code for graphite support which I don't need.
* [statsite] felt very complicated, and was difficult for me to understand
  and modify.
* Wanted support for 'gauges', as recently added to statsD in this
  [pull request][gauges-pull]

## Items of Note
* No imposition of key prefixes. Clients choose their own namespace.
* Imposes key suffixes for all types in order to simplify management of
  Carbon's storage-aggregation.conf and aggregation-rules.conf

## Inspirations
* [statsD]
* [py-statsd]
* [statsite]

[statsD]: https://github.com/etsy/statsd
[gauges-pull]: https://github.com/etsy/statsd/pull/62
[py-statsd]: https://github.com/sivy/py-statsd
[statsite]: https://github.com/kiip/statsite

## Development

This project uses [uv](https://github.com/astral-sh/uv) for dependency management and
[Hatch](https://hatch.pypa.io) as the build backend.
Create a virtual environment and install the project in editable mode with the test extra:

```bash
uv venv
uv pip install -e .[test]
```

Run the unit tests with:

```bash
python -m unittest discover -s tests
```
