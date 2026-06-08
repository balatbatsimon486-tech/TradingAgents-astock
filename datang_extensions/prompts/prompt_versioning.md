# Prompt Versioning

Use this template for each Datang prompt change:

```text
## prompt-name vX.Y.Z

- date:
- upstream commit:
- Datang extension version:
- changed by:
- target task:
- input assumptions:
- output contract affected:
- expected benefit:
- evaluation sample:
- known risk:
- rollback prompt version:
```

Version rules:

- Patch version: wording refinement without output contract changes.
- Minor version: new section, new evidence request, or new analysis role.
- Major version: output schema or downstream adapter behavior changes.

