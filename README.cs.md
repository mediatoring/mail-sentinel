# Mail Sentinel

Lokální AI agent pro prověřování podezřelých e-mailů. Model vybírá ověřovací nástroje a vytváří report s důkazy, chybějícími kontrolami a doporučeními. Změny ve schránce vyžadují samostatné lidské schválení.

**Verze 1.0.0rc2 — kandidát na vydání.** [English](README.md)

## První spuštění

1. Na [GitHubu](https://github.com/mediatoring/mail-sentinel) klikněte na **Code → Download ZIP** a celý archiv rozbalte. Složka se obvykle jmenuje `mail-sentinel-main`.
2. Pokud jej nemáte, nainstalujte **Python 3.11 nebo novější** z [python.org](https://www.python.org/downloads/).
3. Windows: dvakrát klikněte na `START.bat`. macOS/Linux: otevřete terminál v rozbalené složce a spusťte `sh start.sh`.
4. Terminál ponechte otevřený. V prohlížeči otevřete **celou vypsanou lokální adresu**, včetně `#token=…`.
5. Podle [návodu připojte lokální AI](docs/INSTALL.cs.md#první-lokální-model-ai), v Nastavení ověřte spojení a prověřte ukázkový e-mail. Pro lokální AI nepotřebujete schránku ani API klíč.

Na macOS lze při dalších spuštěních použít **Open Mail Sentinel.command**. Použije existující virtuální prostředí nebo Python 3.11+ a otevře aktuální relaci. Po restartu služby použijte spouštěč nebo nově vypsanou adresu; starý token ze záložky už nefunguje.

[Instalace a řešení problémů](docs/INSTALL.cs.md) · [Uživatelský průvodce](docs/USER-GUIDE.cs.md) · [Bezpečnostní omezení](SECURITY.md)

## Vývoj a ověření

```sh
python3 -m unittest discover -s tests -v
python3 -m evaluation.full_eval --config sentinel.toml
```

První příkaz ověřuje chování aplikace. Druhý zpracuje **všech 28 živých scénářů**, včetně vícejazyčných a útočných; vyžaduje nastavený model. Odděleně vykazuje dokončení, bezpečnostní pojistky a správnost očekávaných zjištění. Pro externí AI přidejte `--allow-external`. Volitelné testy adaptéru AgentDojo potřebují `evaluation/requirements.txt`, frontendové testy `jsdom@26`. Viz [ověření](docs/VALIDATION.md).

[Architektura a harness](docs/HARNESS.md) · [Specialisté a ověřená paměť](docs/SKILLS-AND-SUBAGENTS.md) · [Vývojový návod](docs/DEVELOPMENT.md) · [Historie změn](CHANGELOG.md)

Nízké riziko znamená, že provedené kontroly nenašly problém; nejde o záruku bezpečnosti ani schválení platby. Aplikace nezávisle neověřuje identitu odesílatele ani obsah příloh na malware. Maskování citlivých údajů má omezení.

MIT · Michal Kubíček · [Mediatoring](https://mediatoring.cz/kyberbezpecnost/)
