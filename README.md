# Guardian Cloud

**Give AI agents capabilities. Not unrestricted authority.**

Guardian Cloud transforms a supported repository into a deployable application,
passing through a Guardian-based controlled execution layer.

## Conceptual flow

```
repository
→ detection
→ Guardian-controlled execution
→ provisioning
→ deployment
→ public URL
```

## Status

EARLY MVP.

## Guardian Core dependency

Guardian Cloud uses [Guardian Core](https://github.com/AndersonVitaease/memoryos-guardian-core)
as an external dependency, pinned at commit
`e10626c3787a3f4c659a76fa2efb545c9b1f770a`. Guardian Core is not included in
this repository and is not modified by it.

## Install and test

Requires Node.js >= 20.

```
npm install
npm test
```

The published suite runs with `node --import tsx --test` and covers the deploy
entry route, the deploy composition, the application detector, provisioning
input contracts, application domain evidence and the neutral transport.

## License

Source available for evaluation and technical review.
No open-source license is granted at this time.
