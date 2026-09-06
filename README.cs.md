# Mail Sentinel

Lokální AI agent pro prověřování podezřelých e-mailů. Model sám vybírá nástroje, vyhodnocuje jejich výsledky a volí další krok. Python kontroluje oprávnění a předávaná data. Rozhraní je anglicky i česky, licence MIT.

## Spuštění

Potřebujete **Python 3.11+**. Rozbalte ZIP a spusťte `START.bat` na Windows nebo `sh start.sh` na macOS/Linux. V prohlížeči otevřete celou adresu vypsanou v terminálu a připojte model v **Nastavení**. Ukázkové zprávy nepotřebují připojení schránky.

[Instalace krok za krokem pro Windows, macOS a Linux](docs/INSTALL.cs.md)

Podporované připojení: OpenAI API, Anthropic API, Gemini API, lokální OpenAI-kompatibilní server (LM Studio/Ollama) a vlastní HTTPS kompatibilní API. Codex, Claude Code a Cursor lze připojit jako externího klienta přes [MCP](docs/MCP.md); klient používá vlastní model a přihlášení. Webové rozhraní nadále používá API nebo lokální model.

Demo obsahuje pět zpráv a fiktivní evidenci, včetně anglické a české prompt injection a instrukce v názvu přílohy. Analýza vždy používá skutečnou AI. Bez připojení nevznikne žádný předstíraný výsledek.

V `sentinel.toml` nastavte `language = "cs"` pro české výstupy modelu. Jazyk rozhraní lze přepnout nezávisle vpravo nahoře. Nové instalace předávají pseudonymizovaný text pro posouzení významu zprávy. Volitelný `evidence_only` nepředává tělo zprávy modelu. Pro analýzu textu vyberte v Nastavení **Pseudonymizovaný text** a nastavení uložte. Pseudonymizace není zárukou odstranění všech citlivých údajů.

Pro reálnou poštu nastavte IMAP a vlastní `organization.json`. Hesla a API klíče patří do proměnných prostředí, nikoliv do GitHubu. Výchozí přístup ke schránce je pouze pro čtení. Volitelný přesun do karantény vyžaduje schválení člověkem.

Verze 1.0.0rc1 je kandidát na vydání; produkční přijetí vyžaduje ověření v cílovém prostředí. Podrobné funkce, omezení, provoz a testy popisuje [README.md](README.md). Nejde o náhradu poštovní brány ani ověřenou ochranu před všemi phishingovými útoky.

## Vývoj a rozšiřování

Začněte v [návodu pro vývojáře](docs/DEVELOPMENT.md) a [AGENTS.md](AGENTS.md). Přehled změn obsahuje [CHANGELOG.md](CHANGELOG.md).

Autor: [Michal Kubíček](https://kubicek.ai/). Support by [Mediatoring.com](https://mediatoring.cz/kyberbezpecnost/).

Nastavení se přizpůsobuje poskytovateli: lokální AI zobrazuje adresu serveru; OpenAI, Anthropic a Gemini pole pro API klíč; kompatibilní HTTPS API obě pole. Souhlas s externím zpracováním se zobrazuje pouze u cloudových poskytovatelů.

## Pravidla, fronta a rozšíření

V administraci určíte povinné kontroly, necháte výběr na agentovi nebo nástroj vypnete. Platební a firemní pravidla mohou být podmíněná obsahem zprávy. Výsledek obsahuje přehled provedených a chybějících kontrol. Samostatná kontrola prompt injection vrací lokální indikátory; nenalezení vzoru není zárukou bezpečnosti.

Trvalá fronta postupně projde celou nastavenou IMAP složku a obnoví práci po přerušení. Nastavíte datum začátku, souběh, počet pokusů, rychlost, uchování výsledků a limity volání modelu. Frontu a historii lze stránkovat. Po restartu webového serveru je fronta pozastavená; průběžný provoz zajišťuje také `python3 -m sentinel watch` (pro cloud navíc `--allow-external`). [Provoz fronty](docs/QUEUE.md).

V **Rozšíření agenta** lze zapnout uložené skills a specialisty se společným limitem volání. Modely lze načíst z právě vyplněných údajů připojení. IMAP podporuje OAuth2 access token z proměnné `SENTINEL_IMAP_ACCESS_TOKEN`; vydání a obnovu tokenu zajišťuje správce identity.

[Souhrn funkčnosti a ověření verze](docs/RELEASE-1.0.md).


## Firemní pravidla a databáze

V **Nastavení → Pravidla kontroly** zadejte vlastní požadavky na prověřování. LLM posuzuje význam zprávy a použitelnost podmíněných kontrol v jazyce zprávy. Nejisté nebo chybějící posouzení ponechává kontrolu povinnou. Kontrolu nastavenou jako Povinná model nemůže vynechat.

V **Rozšíření agenta → Databázové ověřovací dotazy** nastavte vlastní strukturu dat a parametrizované SQL dotazy. Adaptéry podporují SQLite a PostgreSQL. Každý dotaz se objeví jako samostatný nástroj; výsledky procházejí pseudonymizací. Další konektory lze přidat Python pluginem. Definice pluginu určuje parametry, popis, použitelnost i podmínky dokončení a automaticky se promítne do rozhraní.

Podrobný postup a příklady obsahuje [konfigurace datových zdrojů](docs/DATA-SOURCES.md). Přesnost jazykového rozhodování na zvoleném modelu lze ověřit příkazem `python -m evaluation.semantic_eval`; používá skutečné připojení k AI.

## Kontrola a obnova

`python -m sentinel check` ověří konfiguraci, registraci nástrojů a zapnuté skills bez kontaktování AI. Pokud je zapnutá karanténa, připojí se také k IMAP a ověří cílovou složku a podporu UID MOVE, bez čtení nebo přesunu zpráv. Výstup JSON neobsahuje přihlašovací údaje; návratový kód 2 upozorňuje na nutnou úpravu nastavení. Příkaz `doctor` ověří skutečné volání nástroje modelem.

V Nastavení zadejte kontext skutečně načtený na serveru modelu (`context_tokens`, výchozí hodnota 8 192). Aplikace před požadavkem odhadne velikost vstupu a rezervuje prostor pro výstup. Při překročení limitu nevydá verdikt. Lokální modely s uvažováním mohou potřebovat větší kontext, výstupní limit i čas na odpověď. Podrobnosti popisují [limity modelu](docs/HARNESS.md#context-and-output-budgets).

`python -m sentinel backup backup.sqlite3` vytvoří konzistentní zálohu výsledků a fronty. Nastavení, ověřovací data a přihlašovací údaje zálohujte zvlášť. [Provozní návod](docs/OPERATIONS.md) popisuje obnovu. Datovou složku může používat jeden server, sledování nebo jednorázový scan. Při spuštění `watch` nastavte `queue_since`, nebo přidejte `--entire-folder` pro celou složku.

Pro přijímací testy se skutečným modelem spusťte ze zdrojové složky `python -m evaluation.semantic_eval` a `python -m evaluation.demo_eval`. Používají syntetická data a ukládají výsledky do JSON; externí model navíc vyžaduje `--allow-external`. Vícejazyčný test umožňuje opakovat volbu `--case` a průběžně ukládá výsledky. Naměřené výsledky a zbývající podmínky vydání jsou v [záznamu ověření](docs/VALIDATION.md).

Místní presety schránky a modelu načtete přímo v Nastavení. Pohledy mají vlastní adresy a podporují Zpět/Vpřed i obnovení stránky. Podrobnosti: [místní presety a adresy stránek](docs/LOCAL-PRESETS.md).
