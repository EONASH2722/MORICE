## Summary

Describe the user-visible behavior and why the change is needed.

## Verification

- [ ] `python -m compileall -q morice`
- [ ] `python -m unittest discover -s tests`
- [ ] `pnpm test` in `vnext/`
- [ ] `pnpm run typecheck` in `vnext/`
- [ ] Relevant desktop workflow verified manually

## Safety And Scope

- [ ] No model, secret, cache, build output, or private runtime data is included
- [ ] New renderer output is real, typed, validated, and has an honest failure path
- [ ] File or desktop permissions remain explicit
- [ ] Documentation reflects the actual implementation
