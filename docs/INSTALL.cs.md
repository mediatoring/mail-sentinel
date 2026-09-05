# Instalace

[English](INSTALL.md)

Potřebujete Python 3.11 nebo novější, prohlížeč a lokální AI server s podporou volání nástrojů nebo API klíč a identifikátor modelu. Pro první spuštění nepotřebujete schránku. Aplikace ze stažené složky nevyžaduje instalaci dalších Python balíčků.

## Windows

1. Nainstalujte Python 3.11+ z [python.org](https://www.python.org/downloads/). Pokud instalátor nabídne přidání Pythonu do PATH, zapněte je.
2. ZIP celý rozbalte přes **Extrahovat vše**. Otevřete rozbalenou složku `mail-sentinel`. Nespouštějte aplikaci přímo z náhledu ZIPu.
3. Dvakrát klikněte na `START.bat`. Okno terminálu nechte otevřené.
4. V prohlížeči otevřete celou vypsanou lokální adresu, včetně části `#token=…`.

Pokud spuštění dvojklikem nefunguje, otevřete ve složce projektu PowerShell a spusťte:

```powershell
py -3 --version
py -3 -m sentinel serve
```

Pokud příkaz `py` chybí, zkuste `python --version` a `python -m sentinel serve`. Spouštěč zkouší obě možnosti. Verzi starší než 3.11 aktualizujte. Po instalaci otevřete terminál znovu, aby načetl změnu PATH.

## macOS

Pokud potřebujete Python 3.11+, nainstalujte jej z [python.org](https://www.python.org/downloads/macos/). Rozbalte ZIP, otevřete Terminál, napište `cd `, přetáhněte do něj rozbalenou složku `mail-sentinel` a stiskněte Return. Pak spusťte:

```sh
python3 --version
sh start.sh
```

Terminál nechte otevřený a v prohlížeči otevřete celou vypsanou adresu. Příkaz `sh start.sh` funguje i tehdy, když se při rozbalení nezachovalo oprávnění ke spuštění souboru.

## Linux

Podle potřeby nainstalujte Python 3.11+ správcem balíčků své distribuce. Rozbalte ZIP a otevřete terminál ve složce `mail-sentinel`:

```sh
python3 --version
sh start.sh
```

Pokud distribuce obsahuje starší Python, nainstalujte podporovanou verzi postupem pro danou distribuci. Ručně nenahrazujte systémový Python. Ke spuštění aplikace nepotřebujete `sudo`.

## Připojení AI a první analýza

1. Přepněte rozhraní nahoře na češtinu. Vyberte **Vyzkoušet ukázkový e-mail**, **Otevřít soubor .eml** nebo **Připojit schránku**. Ukázkové zprávy obsahují vlastní fiktivní evidenci.
2. Otevřete **Nastavení → Připojení AI**. Vyberte poskytovatele. Pro lokální AI spusťte modelový server a vyberte **LM Studio**, **Ollama** nebo vlastní lokální adresu. Pro cloudovou AI zadejte API klíč a povolte externí zpracování.
3. Klikněte na **Načíst dostupné modely** a vyberte model, případně zadejte jeho přesné ID. Tlačítko používá údaje právě vyplněné ve formuláři.
4. Vyberte **Pouze lokálně zjištěné údaje**, pokud chcete předávat lokální zjištění a ponechat text e-mailu v aplikaci, nebo **Pseudonymizovaný text** pro analýzu maskovaného textu. Maskování nemusí zachytit všechny citlivé údaje. Nastavte jazyk výsledku.
5. Klikněte na **Ověřit a uložit připojení AI**. Test skutečně volá model a poskytovatel jej může účtovat. Potvrzuje spojení a volání nástrojů; neměří přesnost detekce. **Uložit připojení** uloží údaje bez ověřovacího volání modelu.
6. V **Kontrola zpráv** vyberte zprávu. Přečtěte její text a rozsah analýzy. Pro externí AI zobrazte **Zkontrolovat předávaná data**, projděte jednotlivé položky a potvrďte souhlas. Klikněte na **Prověřit pomocí AI**.
7. Přečtěte závěr, přehled provedených kontrol a doporučení. Technické důkazy jsou pod **Průběh prověřování**. Uložené výsledky najdete v **Poslední analýzy**; obnovení stránky naváže na běžící analýzu.

Pro schránku vyplňte **Nastavení → Schránka a firemní evidence** a uložte nastavení. Složku ke kontrole nejprve vytvořte na poštovním serveru. IMAP používá TLS a heslo / heslo aplikace nebo správcem vydaný OAuth2 access token. Vydání a obnovu tokenu zajišťuje správce identity.

V **Pravidla kontroly** vyberte **Obecné bezpečnostní kontroly** pro lokální indikátory, nebo **Bezpečnost a firemní evidence**, pokud máte schválené ověřovací údaje. Profil použijte uložením nastavení. Povinné kontroly vůči evidenci potřebují firemní soubor JSON; chybějící podklady se ukážou před analýzou a brání závěru o nízkém riziku, pokud povinnou kontrolu nelze ověřit. Obecný profil neověřuje dodavatele a platební účty vůči evidenci.

Pro průběžný provoz otevřete **Sledování schránky**. V **Rozsah zpracování a limity** nastavte počáteční datum, případně na obrazovce sledování výslovně zahrňte celou složku. Před spuštěním zkontrolujte zobrazený rozsah a limity. Z položek fronty otevřete výsledky. Stav rozlišuje zpracování, čekání na limit, opakování pokusu a čekání na novou poštu.

## Ukončení a další spuštění

Aplikaci ukončíte přes Ctrl+C v terminálu. Při dalším spuštění použijte stejný spouštěč a nově vypsanou adresu. Nastavení a výsledky zůstanou ve složce projektu; klíče a hesla zadané v prohlížeči je po restartu nutné zadat znovu. Složku projektu proto ponechte na místě.

Pro automatický provoz a proměnné prostředí slouží [provozní návod](OPERATIONS.md). Volitelného terminálového průvodce spustíte přes `python3 -m sentinel setup`, na Windows `py -3 -m sentinel setup`. Průvodce existující nastavení nepřepíše.

## Když se něco nedaří

| Problém | Řešení |
| --- | --- |
| `No module named sentinel` | Přejděte do složky obsahující podsložku `sentinel` a soubor `pyproject.toml`. |
| Chybí `tomllib` | Používáte Python starší než 3.11. Ověřte verzi a aktualizujte jej. |
| Port je obsazený | Ukončete předchozí běh nebo použijte `python3 -m sentinel serve --port 8766`, na Windows `py -3` místo `python3`. |
| Neautorizovaný přístup / prázdná fronta | Otevřete celou aktuální adresu z terminálu. Token minulého běhu už neplatí. |
| Lokální model odmítá spojení | Zapněte jeho server, načtěte model a ověřte adresu i port. |
| Test volání nástroje selhal | Ověřte ID modelu a podporu nativního volání nástrojů. Samotná schopnost chatovat nestačí. |
| Externí zpracování je zamítnuté | Uložte jeho povolení a API klíč; před analýzou zobrazte data a potvrďte souhlas. |
| IMAP se nepřihlásí | Ověřte server, jméno a heslo aplikace. Zjistěte u správce, zda povoluje IMAP s heslem. |

Aplikace běží pouze na daném počítači. Adresa otevřená na telefonu se k aplikaci v počítači nepřipojí.

[Check rules / Pravidla kontrol](CHECKS.md) · [Queue / Fronta](QUEUE.md) · [MCP](MCP.md)


## Vlastní firemní pravidla a SQL evidence

V **Pravidla kontroly → Požadavky na prověřování** popište, co má agent ověřovat. V **Rozšíření agenta → Databázové ověřovací dotazy** vyplňte konfiguraci podle [příkladu SQLite](../examples/data-sources.sqlite.json) nebo [PostgreSQL](../examples/data-sources.postgresql.json). Použijte vlastní názvy tabulek, sloupců a význam parametrů. Po uložení se dotazy objeví v pravidlech kontrol.

U SQL evidence vypněte kontroly lokálního dodavatelského adaptéru, které nepoužíváte, a nastavte režimy nových dotazů. Přihlašovací údaje PostgreSQL nastavte v proměnné prostředí uvedené v konfiguraci zdroje; do editoru patří pouze název proměnné. Oprávnění k databázi nastavuje její správce. Podrobnosti: [Datové zdroje](DATA-SOURCES.md).

## Kontrola nastavení a zálohy

Z rozbalené složky spusťte `python3 -m sentinel check`, na Windows `py -3 -m sentinel check`. Příkaz načte rozšíření a zkontroluje povinnou lokální evidenci bez odesílání e-mailu AI. Vyřešte neúspěšné kontroly a v Nastavení ověřte připojení modelu.

Stejnou datovou složku může používat jeden proces. Před dalším spuštěním předchozí proces ukončete. Pokud HTTP port používá jiná aplikace, vyberte jiný přes `serve --port 8766`.

Zálohu výsledků a fronty vytvoříte přes `python3 -m sentinel backup backup.sqlite3`, na Windows `py -3`. Cílový soubor nesmí existovat. Nastavení a ověřovací zdroje zálohujte zvlášť; postup obnovy je v [provozním návodu](OPERATIONS.md).
