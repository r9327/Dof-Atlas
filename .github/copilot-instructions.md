# GitHub Copilot entrypoint

Read `/AI_ENTRYPOINT.md` before editing. Start non-trivial work with
`py -3.13 -X utf8 -m tools.atlas_doctor agent plan <paths> --base-ref HEAD --json`
and obey the returned edit contract, checks and forbidden claims.

For **every** PR: keep Draft until the entire scope and focused local tests
are complete. Do not run GitHub CI on intermediate commits. Mark Ready for
review only when the final candidate is complete; certify that exact SHA once,
then fix and recertify only if necessary. Read AGENTS.md for the global rule.
