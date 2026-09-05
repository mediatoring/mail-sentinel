# Check rules and semantic applicability

The model interprets message meaning, requested actions and manipulation attempts in the language of the message. It chooses tools from their registered descriptions. Administrator requirements and plugin metadata define what a complete investigation must establish.

| Mode | Effect |
| --- | --- |
| Required | Missing or unavailable evidence prevents a low-risk conclusion. The model cannot waive this check. |
| Agent decides | The model selects the tool when useful. |
| Disabled | The tool is absent from the callable registry. |
| When applicable | The model assesses relevance from message meaning and the plugin's applicability description. Missing or uncertain assessments leave the check required. |

The model can call `assess_applicability` to classify every conditional check as applicable, not applicable or uncertain, with a reason. It can also perform a check directly. An assessment is recorded as a model judgment, not independent evidence. A false-negative judgment remains possible; use Required for checks that must apply to every message.

Message inspection is mandatory. Built-in checks and installed plugins supply their own default modes, availability checks and reasons that prevent a low-risk verdict. The same catalog drives model definitions, administrator controls, previews and report completion. Custom plugin names do not require edits to the UI or the rule engine.

New configurations use pseudonymized message text so the model can assess meaning. Existing privacy settings remain in effect. Evidence-only mode withholds text and cannot waive semantic checks; truncated text also prevents a waiver. Choose local inference when the permitted disclosure does not allow sending pseudonymized text externally.

## Organization requirements

Enter ordinary-language investigation requirements in Settings → Check rules. Configure the evidence tools needed to verify those requirements and choose their modes. Textual instructions guide the model; Required modes and plugin completion checks provide host-enforced requirements. A textual policy alone is not a deterministic business-rule engine.

[Database evidence sources](DATA-SOURCES.md) can query an organization's own schema. Retrieved policy records are paginated and assessed semantically.

## Results and prompt injection

Reports distinguish a finished investigation, check coverage and risk findings. Missing required evidence or a plugin blocker prevents LOW_RISK and replaces contradictory low-risk advice. The report records effective check modes and configuration hashes for traceability.

The model is instructed to assess prompt injection semantically in all message languages. The bundled pattern plugin supplies additional known indicators from subject, parsed body and attachment names. Its patterns do not determine payment relevance or the language of the investigation. No pattern match is not proof of safety. Attachments are not opened or executed.

For real-model language acceptance, run:

```sh
python3 -m evaluation.semantic_eval --config sentinel.toml
# Add --allow-external for an explicitly authorized external provider.
```

The suite uses synthetic German, Slovak, Polish, French, Japanese and Arabic messages plus non-payment controls. It requires a configured real model and can incur provider charges. Its results concern these cases and this model configuration, not universal language accuracy or security certification.

The live acceptance command accepts repeatable `--case` selectors (for example `--case de_payment --case de_greeting`). It checkpoints completed cases to the output file after each investigation; the JSON contains `completed: true` only after the selected set finishes. A matching applicability flag from an incomplete run is not a passing case.
