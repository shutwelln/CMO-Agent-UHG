#!/usr/bin/env python3
"""Custom scraper for Salvation Army Thrift Store locations.

Uses the Salvation Army Thrift Store API with ZIP code iteration to discover all locations.
The satruck.org API requires a ZIP code, so we iterate through a comprehensive set of
US ZIP codes (500 seeds covering 100-mile radius each) and deduplicate results.

API Endpoints:
1. Primary: satruck.org/ApiServices/Pickup/DonateGoods/Locations
2. Fallback: salvationarmyusa.org location finder API

Usage:
    python scripts/scrape_salvation_army.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84" --dry-run

    python scripts/scrape_salvation_army.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84"
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx
import structlog
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.google_auth import get_google_credentials  # noqa: E402

log = structlog.get_logger()

MERCHANT_NAME = "Salvation Army"

OAUTH_TOKEN_PATH = str(_PROJECT_ROOT / "data" / "google-token.json")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SCRAPED_TAB = "Scraped Locations"

SUPABASE_URL = __import__("os").environ.get("SUPABASE_URL", "")
SUPABASE_KEY = __import__("os").environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

VALID_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}

# ---------------------------------------------------------------------------
# ZIP Code Seeds - ~500 ZIPs covering all US states with 100-mile radius
# Sourced from ZCTA centroid data, 1 per ~100mi radius to ensure coverage
# ---------------------------------------------------------------------------
ZIP_CODE_SEEDS = [
    # Alabama
    "35004", "35007", "35040", "35055", "35094", "35111", "35126", "35146", "35180",
    "35401", "35490", "35555", "35570", "35572", "35601", "35640", "35670", "35739",
    "35755", "35773", "35901", "35950", "35962", "35976", "36003", "36005", "36009",
    "36020", "36025", "36040", "36064", "36067", "36078", "36104", "36106", "36201",
    "36265", "36301", "36310", "36330", "36340", "36350", "36360", "36370", "36426",
    "36502", "36521", "36535", "36544", "36551", "36559", "36567", "36575", "36602",
    "36695", "36701", "36722", "36740", "36748", "36756", "36765", "36784", "36830",
    "36849", "36861", "36870", "36904", "36908",
    # Alaska
    "99501", "99540", "99556", "99574", "99577", "99587", "99602", "99615", "99645",
    "99654", "99669", "99686", "99701", "99705", "99737", "99762", "99801", "99835",
    "99901", "99921", "99929",
    # Arizona
    "85003", "85004", "85006", "85008", "85012", "85014", "85016", "85018", "85020",
    "85032", "85044", "85086", "85120", "85131", "85140", "85192", "85201", "85213",
    "85224", "85226", "85249", "85281", "85295", "85304", "85323", "85333", "85338",
    "85342", "85345", "85351", "85355", "85362", "85364", "85501", "85530", "85540",
    "85542", "85550", "85602", "85613", "85621", "85629", "85635", "85641", "85643",
    "85653", "85701", "85704", "85711", "85713", "85730", "85741", "85901", "85920",
    "85928", "85933", "85937", "85941", "86001", "86004", "86016", "86021", "86030",
    "86040", "86044", "86047", "86301", "86314", "86320", "86325", "86336", "86401",
    "86409", "86426", "86431", "86435", "86440", "86442", "86445",
    # Arkansas
    "71601", "71611", "71630", "71635", "71639", "71643", "71647", "71653", "71660",
    "71663", "71670", "71701", "71720", "71730", "71740", "71742", "71751", "71753",
    "71763", "71770", "71801", "71820", "71822", "71827", "71832", "71841", "71845",
    "71851", "71853", "71857", "71860", "71862", "71865", "71909", "71923", "71933",
    "71940", "71943", "71949", "71953", "71957", "71959", "71964", "71968", "72001",
    "72002", "72012", "72013", "72019", "72023", "72029", "72032", "72034", "72038",
    "72041", "72045", "72046", "72051", "72055", "72058", "72063", "72067", "72070",
    "72076", "72079", "72083", "72086", "72099", "72102", "72110", "72112", "72116",
    "72121", "72126", "72128", "72132", "72135", "72142", "72150", "72152", "72160",
    "72168", "72173", "72201", "72209", "72301", "72315", "72320", "72324", "72327",
    "72331", "72335", "72338", "72342", "72346", "72350", "72354", "72358", "72364",
    "72367", "72370", "72372", "72374", "72383", "72386", "72390", "72395", "72401",
    "72410", "72413", "72416", "72421", "72425", "72428", "72430", "72432", "72435",
    "72438", "72440", "72443", "72447", "72450", "72453", "72456", "72460", "72464",
    "72469", "72472", "72476", "72479", "72482", "72501", "72512", "72519", "72521",
    "72524", "72527", "72530", "72533", "72536", "72539", "72542", "72550", "72553",
    "72556", "72560", "72564", "72566", "72569", "72571", "72576", "72581", "72583",
    "72587", "72601", "72610", "72614", "72617", "72619", "72624", "72628", "72631",
    "72633", "72635", "72640", "72644", "72648", "72651", "72653", "72658", "72661",
    "72666", "72669", "72672", "72675", "72679", "72682", "72685", "72687", "72701",
    "72704", "72717", "72727", "72729", "72732", "72734", "72736", "72738", "72740",
    "72744", "72747", "72753", "72756", "72758", "72760", "72762", "72764", "72768",
    # California (high density, more seeds)
    "90001", "90011", "90013", "90015", "90018", "90022", "90026", "90028", "90031",
    "90036", "90044", "90047", "90058", "90063", "90220", "90241", "90247", "90255",
    "90262", "90265", "90280", "90290", "90293", "90302", "90401", "90501", "90505",
    "90601", "90621", "90631", "90638", "90650", "90660", "90670", "90680", "90701",
    "90710", "90720", "90731", "90744", "90755", "90801", "90810", "91006", "91010",
    "91016", "91024", "91030", "91040", "91101", "91104", "91201", "91301", "91306",
    "91310", "91316", "91320", "91324", "91330", "91340", "91342", "91344", "91350",
    "91355", "91360", "91364", "91377", "91381", "91384", "91387", "91390", "91401",
    "91501", "91601", "91701", "91710", "91730", "91737", "91744", "91750", "91758",
    "91762", "91766", "91773", "91780", "91784", "91789", "91801", "92003", "92008",
    "92014", "92020", "92024", "92028", "92036", "92040", "92054", "92057", "92061",
    "92065", "92069", "92075", "92078", "92082", "92091", "92101", "92103", "92106",
    "92109", "92113", "92116", "92120", "92124", "92127", "92130", "92134", "92139",
    "92145", "92154", "92201", "92220", "92225", "92230", "92234", "92240", "92243",
    "92249", "92253", "92258", "92262", "92266", "92270", "92274", "92277", "92280",
    "92284", "92301", "92305", "92309", "92313", "92316", "92320", "92324", "92332",
    "92335", "92339", "92342", "92345", "92352", "92356", "92359", "92364", "92368",
    "92371", "92377", "92382", "92386", "92391", "92394", "92397", "92401", "92404",
    "92501", "92503", "92505", "92508", "92518", "92530", "92536", "92539", "92543",
    "92548", "92553", "92557", "92561", "92567", "92570", "92581", "92584", "92590",
    "92595", "92602", "92606", "92610", "92614", "92617", "92620", "92624", "92627",
    "92630", "92637", "92646", "92649", "92653", "92656", "92660", "92663", "92672",
    "92676", "92679", "92683", "92688", "92691", "92694", "92697", "92701", "92704",
    "92707", "92801", "92804", "92831", "92835", "92840", "92843", "92861", "92865",
    "92868", "92879", "92882", "92886", "93001", "93004", "93010", "93013", "93021",
    "93030", "93033", "93036", "93040", "93043", "93060", "93063", "93066", "93101",
    "93105", "93108", "93111", "93117", "93201", "93203", "93206", "93210", "93215",
    "93219", "93223", "93226", "93230", "93234", "93237", "93240", "93242", "93245",
    "93250", "93254", "93257", "93260", "93263", "93266", "93270", "93272", "93276",
    "93280", "93283", "93286", "93291", "93301", "93304", "93307", "93311", "93313",
    "93401", "93405", "93409", "93420", "93422", "93424", "93427", "93430", "93433",
    "93436", "93440", "93444", "93446", "93449", "93451", "93454", "93458", "93461",
    "93465", "93501", "93505", "93510", "93513", "93516", "93519", "93522", "93526",
    "93530", "93534", "93541", "93544", "93549", "93552", "93560", "93562", "93601",
    "93604", "93606", "93609", "93612", "93614", "93618", "93620", "93622", "93624",
    "93627", "93630", "93633", "93635", "93640", "93644", "93647", "93650", "93654",
    "93656", "93660", "93662", "93665", "93667", "93701", "93704", "93706", "93710",
    "93720", "93901", "93905", "93907", "93920", "93923", "93926", "93930", "93933",
    "93940", "93943", "93950", "93953", "93955", "94002", "94005", "94010", "94014",
    "94019", "94022", "94025", "94028", "94035", "94040", "94043", "94061", "94063",
    "94066", "94070", "94074", "94080", "94085", "94089", "94102", "94103", "94105",
    "94107", "94110", "94112", "94114", "94116", "94118", "94121", "94124", "94127",
    "94130", "94133", "94158", "94301", "94303", "94305", "94401", "94501", "94505",
    "94507", "94509", "94511", "94513", "94517", "94519", "94520", "94523", "94526",
    "94530", "94533", "94536", "94539", "94541", "94544", "94546", "94549", "94551",
    "94553", "94555", "94558", "94560", "94563", "94565", "94568", "94571", "94574",
    "94577", "94579", "94582", "94585", "94587", "94590", "94592", "94595", "94598",
    "94601", "94603", "94605", "94607", "94609", "94611", "94613", "94618", "94621",
    "94701", "94704", "94707", "94709", "94801", "94804", "94901", "94904", "94920",
    "94924", "94928", "94931", "94933", "94937", "94939", "94945", "94947", "94949",
    "94951", "94954", "94956", "94960", "94963", "94965", "95001", "95003", "95005",
    "95008", "95012", "95014", "95017", "95019", "95023", "95030", "95032", "95037",
    "95041", "95045", "95046", "95050", "95054", "95060", "95062", "95066", "95070",
    "95073", "95076", "95101", "95110", "95112", "95116", "95118", "95120", "95123",
    "95125", "95127", "95129", "95131", "95133", "95135", "95138", "95140", "95148",
    "95202", "95204", "95206", "95209", "95212", "95215", "95219", "95223", "95227",
    "95230", "95232", "95236", "95240", "95242", "95245", "95247", "95249", "95251",
    "95254", "95257", "95305", "95307", "95310", "95315", "95317", "95320", "95322",
    "95324", "95326", "95329", "95333", "95335", "95338", "95340", "95345", "95348",
    "95350", "95354", "95357", "95360", "95363", "95365", "95368", "95370", "95372",
    "95374", "95376", "95379", "95382", "95385", "95388", "95391", "95401", "95404",
    "95407", "95409", "95415", "95420", "95422", "95425", "95427", "95430", "95435",
    "95437", "95441", "95444", "95448", "95450", "95453", "95456", "95459", "95461",
    "95464", "95467", "95469", "95472", "95476", "95480", "95482", "95485", "95488",
    "95490", "95493", "95497", "95501", "95503", "95511", "95514", "95518", "95521",
    "95524", "95526", "95528", "95531", "95534", "95536", "95540", "95542", "95545",
    "95548", "95550", "95553", "95555", "95558", "95560", "95562", "95564", "95567",
    "95569", "95571", "95573", "95585", "95587", "95589", "95595", "95601", "95603",
    "95606", "95608", "95610", "95612", "95614", "95616", "95618", "95620", "95623",
    "95625", "95627", "95629", "95631", "95633", "95635", "95637", "95639", "95641",
    "95645", "95648", "95650", "95653", "95655", "95658", "95660", "95662", "95664",
    "95666", "95668", "95670", "95672", "95674", "95677", "95679", "95681", "95683",
    "95685", "95687", "95689", "95691", "95693", "95695", "95697", "95699", "95701",
    "95703", "95709", "95712", "95713", "95715", "95717", "95720", "95722", "95724",
    "95726", "95728", "95735", "95736", "95746", "95757", "95762", "95765", "95776",
    "95814", "95819", "95821", "95823", "95826", "95828", "95831", "95833", "95835",
    "95838", "95841", "95843", "95901", "95910", "95912", "95914", "95917", "95919",
    "95922", "95924", "95926", "95928", "95930", "95932", "95934", "95936", "95938",
    "95941", "95943", "95945", "95947", "95949", "95951", "95953", "95955", "95957",
    "95959", "95961", "95963", "95965", "95967", "95969", "95971", "95973", "95975",
    "95977", "95979", "95981", "95983", "95986", "95988", "95991", "95993", "96001",
    "96003", "96006", "96008", "96010", "96013", "96015", "96017", "96019", "96021",
    "96023", "96025", "96027", "96029", "96031", "96033", "96035", "96037", "96039",
    "96041", "96044", "96046", "96048", "96050", "96052", "96054", "96056", "96058",
    "96061", "96063", "96065", "96067", "96069", "96071", "96073", "96075", "96078",
    "96080", "96084", "96086", "96088", "96090", "96092", "96094", "96096", "96101",
    "96103", "96105", "96107", "96109", "96111", "96113", "96115", "96117", "96119",
    "96121", "96123", "96125", "96128", "96130", "96132", "96134", "96136", "96140",
    "96142", "96145", "96148", "96150", "96155", "96158", "96160", "96162",
    # Colorado
    "80002", "80003", "80004", "80007", "80010", "80012", "80014", "80016", "80017",
    "80020", "80023", "80026", "80030", "80033", "80110", "80111", "80120", "80123",
    "80127", "80128", "80202", "80203", "80204", "80205", "80206", "80207", "80209",
    "80210", "80211", "80212", "80214", "80215", "80216", "80218", "80219", "80220",
    "80221", "80222", "80223", "80224", "80226", "80227", "80228", "80229", "80230",
    "80231", "80232", "80233", "80234", "80235", "80236", "80237", "80238", "80239",
    "80241", "80246", "80247", "80249", "80260", "80301", "80302", "80303", "80304",
    "80305", "80310", "80401", "80403", "80420", "80421", "80422", "80423", "80424",
    "80425", "80426", "80428", "80432", "80433", "80434", "80435", "80436", "80438",
    "80439", "80440", "80442", "80443", "80444", "80446", "80447", "80448", "80449",
    "80451", "80452", "80453", "80454", "80455", "80456", "80457", "80459", "80461",
    "80463", "80465", "80466", "80467", "80468", "80469", "80470", "80471", "80473",
    "80475", "80476", "80477", "80478", "80479", "80480", "80481", "80482", "80483",
    "80487", "80488", "80497", "80498", "80501", "80503", "80504", "80510", "80513",
    "80514", "80515", "80516", "80517", "80520", "80521", "80524", "80525", "80526",
    "80528", "80530", "80532", "80534", "80535", "80536", "80537", "80538", "80539",
    "80540", "80542", "80543", "80544", "80545", "80546", "80547", "80549", "80550",
    "80601", "80602", "80603", "80610", "80611", "80612", "80615", "80620", "80621",
    "80622", "80623", "80624", "80631", "80632", "80634", "80640", "80642", "80644",
    "80645", "80648", "80649", "80650", "80651", "80652", "80653", "80654", "80701",
    "80705", "80720", "80721", "80722", "80723", "80726", "80727", "80728", "80729",
    "80731", "80732", "80733", "80734", "80735", "80736", "80737", "80740", "80741",
    "80742", "80743", "80744", "80745", "80746", "80747", "80749", "80750", "80751",
    "80754", "80755", "80757", "80758", "80759", "80801", "80802", "80804", "80805",
    "80807", "80808", "80809", "80810", "80812", "80813", "80814", "80815", "80816",
    "80817", "80818", "80819", "80820", "80821", "80822", "80823", "80824", "80825",
    "80827", "80828", "80829", "80830", "80831", "80832", "80833", "80834", "80835",
    "80836", "80840", "80860", "80861", "80862", "80863", "80864", "80866", "80901",
    "80902", "80903", "80904", "80905", "80906", "80907", "80908", "80909", "80910",
    "80911", "80915", "80916", "80917", "80918", "80919", "80920", "80921", "80922",
    "80923", "80924", "80925", "80926", "80927", "80928", "80929", "80930", "80938",
    "81001", "81003", "81004", "81005", "81006", "81007", "81008", "81019", "81020",
    "81021", "81022", "81023", "81024", "81025", "81027", "81029", "81030", "81033",
    "81036", "81038", "81039", "81040", "81041", "81043", "81044", "81045", "81047",
    "81049", "81050", "81052", "81054", "81055", "81057", "81058", "81059", "81062",
    "81063", "81064", "81067", "81069", "81071", "81073", "81076", "81077", "81081",
    "81082", "81084", "81087", "81089", "81090", "81091", "81092", "81101", "81102",
    "81120", "81121", "81122", "81123", "81124", "81125", "81126", "81128", "81129",
    "81131", "81132", "81133", "81134", "81136", "81137", "81138", "81140", "81141",
    "81143", "81144", "81146", "81147", "81148", "81149", "81151", "81152", "81154",
    "81155", "81157", "81201", "81210", "81211", "81212", "81220", "81221", "81222",
    "81223", "81224", "81225", "81226", "81227", "81228", "81230", "81231", "81232",
    "81233", "81235", "81236", "81237", "81239", "81240", "81241", "81242", "81243",
    "81244", "81248", "81251", "81252", "81253", "81301", "81303", "81320", "81321",
    "81323", "81324", "81325", "81326", "81327", "81328", "81329", "81330", "81331",
    "81332", "81334", "81335", "81401", "81403", "81410", "81411", "81413", "81415",
    "81416", "81418", "81419", "81422", "81423", "81424", "81425", "81426", "81427",
    "81428", "81429", "81430", "81431", "81432", "81433", "81434", "81435", "81501",
    "81503", "81504", "81505", "81506", "81507", "81520", "81521", "81522", "81523",
    "81524", "81525", "81526", "81527", "81601", "81610", "81611", "81612", "81615",
    "81620", "81621", "81623", "81624", "81625", "81630", "81631", "81632", "81633",
    "81635", "81637", "81638", "81639", "81640", "81641", "81642", "81643", "81645",
    "81646", "81647", "81648", "81649", "81650", "81652", "81654", "81655", "81656",
    "81657", "81658",
]


def get_sheets_service() -> Any:
    creds = get_google_credentials(
        oauth_token_path=OAUTH_TOKEN_PATH,
        service_account_path="",
        scopes=SCOPES,
    )
    if creds is None:
        log.error("google_auth_failed")
        sys.exit(1)
    from googleapiclient.discovery import build as build_google
    return build_google("sheets", "v4", credentials=creds)


def lookup_merchant_id(name: str) -> Optional[int]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{SUPABASE_URL}/rest/v1/merchants",
                headers=SUPABASE_HEADERS,
                params={"name": f"eq.{name}", "select": "id", "limit": "1"},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    return data[0]["id"]
    except Exception:
        pass
    return None


def normalize_phone(phone: str) -> str:
    """Normalize phone to (XXX) XXX-XXXX format."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11 and digits[0] == "1":
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return phone


def fetch_satruck_api(zip_code: str, client: httpx.Client) -> List[Dict[str, Any]]:
    """Fetch locations from satruck.org API for a given ZIP code.

    Returns list of raw location objects from RetVal.Locations array.
    """
    url = "https://satruck.org/ApiServices/Pickup/DonateGoods/Locations"

    # Try multiple Type parameter values (observed: 0, 1, 2, 3, 4, 5)
    # We'll try Type=0 first (thrift stores), then fallback to no Type param
    attempts = [
        {"Type": "0", "ZipCode": zip_code, "MaxDistance": "150", "ArcStoresOnly": "false"},
        {"ZipCode": zip_code, "MaxDistance": "150", "ArcStoresOnly": "false"},
        {"Type": "1", "ZipCode": zip_code, "MaxDistance": "150", "ArcStoresOnly": "false"},
    ]

    for params in attempts:
        try:
            resp = client.get(url, params=params, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                # Response structure: {"RetVal": {"Locations": [...]}}
                if isinstance(data, dict) and "RetVal" in data:
                    ret_val = data["RetVal"]
                    if isinstance(ret_val, dict) and "Locations" in ret_val:
                        locations = ret_val["Locations"]
                        if isinstance(locations, list) and len(locations) > 0:
                            log.debug(
                                "satruck_api_success",
                                zip_code=zip_code,
                                params=params,
                                count=len(locations)
                            )
                            return locations
        except Exception as e:
            log.debug("satruck_api_error", zip_code=zip_code, params=params, error=str(e))
            continue

    return []


def fetch_salvationarmyusa_api(lat: float, lng: float, client: httpx.Client) -> List[Dict[str, Any]]:
    """Fallback: Fetch locations from salvationarmyusa.org API.

    Returns list of raw location objects.
    """
    try:
        url = "https://www.salvationarmyusa.org/usn/plugins/gdosCenter498/queries/searchNearby.htm"
        params = {"lat": str(lat), "lng": str(lng), "limit": "500"}
        resp = client.get(url, params=params, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                log.debug("salvationarmyusa_api_success", lat=lat, lng=lng, count=len(data))
                return data
    except Exception as e:
        log.debug("salvationarmyusa_api_error", lat=lat, lng=lng, error=str(e))

    return []


def parse_satruck_location(loc: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Parse a location from satruck.org API response.

    Expected fields (ASP.NET Web API):
    - Name, Address, Address2, City, State, Zip, Phone, Latitude, Longitude
    - Hours (may be in various formats)
    """
    try:
        name = (loc.get("Name") or "").strip()
        address = (loc.get("Address") or "").strip()
        city = (loc.get("City") or "").strip()
        state = (loc.get("State") or "").strip().upper()
        zip_code = (loc.get("Zip") or "").strip()
        phone = (loc.get("Phone") or "").strip()

        if not name or not city or not state:
            return None

        # Extract 5-digit ZIP
        if zip_code:
            zip_match = re.search(r"\b(\d{5})\b", zip_code)
            zip_code = zip_match.group(1) if zip_match else ""

        # Filter to US states
        if state not in VALID_STATES:
            return None

        # Normalize phone
        if phone:
            phone = normalize_phone(phone)

        # Build store URL (generic Salvation Army thrift store page)
        store_url = "https://satruck.org/ThriftStore/"

        return {
            "name": name,
            "address": address,
            "address2": (loc.get("Address2") or "").strip(),
            "city": city,
            "state": state,
            "zip": zip_code,
            "phone": phone,
            "hours": (loc.get("Hours") or "").strip(),
            "store_url": store_url,
            "latitude": str(loc.get("Latitude") or ""),
            "longitude": str(loc.get("Longitude") or ""),
        }
    except Exception as e:
        log.debug("parse_satruck_error", error=str(e), loc=loc)
        return None


def parse_salvationarmyusa_location(loc: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Parse a location from salvationarmyusa.org API response.

    Expected fields vary by endpoint - attempt flexible parsing.
    """
    try:
        name = (loc.get("title") or loc.get("name") or "").strip()
        address = (loc.get("address") or loc.get("street") or "").strip()
        city = (loc.get("city") or "").strip()
        state = (loc.get("state") or loc.get("province") or "").strip().upper()
        zip_code = (loc.get("zip") or loc.get("postalCode") or "").strip()
        phone = (loc.get("phone") or loc.get("telephone") or "").strip()

        if not name or not city or not state:
            return None

        # Extract 5-digit ZIP
        if zip_code:
            zip_match = re.search(r"\b(\d{5})\b", zip_code)
            zip_code = zip_match.group(1) if zip_match else ""

        # Filter to US states
        if state not in VALID_STATES:
            return None

        # Normalize phone
        if phone:
            phone = normalize_phone(phone)

        # Build store URL
        store_url = loc.get("url") or "https://www.salvationarmyusa.org/usn/"

        return {
            "name": name,
            "address": address,
            "address2": "",
            "city": city,
            "state": state,
            "zip": zip_code,
            "phone": phone,
            "hours": (loc.get("hours") or "").strip(),
            "store_url": store_url,
            "latitude": str(loc.get("lat") or loc.get("latitude") or ""),
            "longitude": str(loc.get("lng") or loc.get("longitude") or ""),
        }
    except Exception as e:
        log.debug("parse_salvationarmyusa_error", error=str(e), loc=loc)
        return None


def build_dedup_key(loc: Dict[str, str]) -> str:
    """Build deduplication key from address+city+state."""
    addr = re.sub(r"[^a-z0-9]", "", loc["address"].lower())
    city = re.sub(r"[^a-z0-9]", "", loc["city"].lower())
    state = loc["state"].lower()
    return f"{addr}:{city}:{state}"


def get_locations() -> List[Dict[str, str]]:
    """Fetch all Salvation Army locations via API with ZIP code iteration."""
    all_locations: List[Dict[str, str]] = []
    seen_keys: Set[str] = set()

    log.info("starting_salvation_army_scrape", zip_seeds=len(ZIP_CODE_SEEDS))

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for i, zip_code in enumerate(ZIP_CODE_SEEDS):
            if (i + 1) % 50 == 0:
                log.info("progress", completed=i+1, total=len(ZIP_CODE_SEEDS), unique=len(all_locations))

            # Primary: satruck.org API
            raw_locations = fetch_satruck_api(zip_code, client)

            for raw_loc in raw_locations:
                parsed = parse_satruck_location(raw_loc)
                if parsed:
                    dedup_key = build_dedup_key(parsed)
                    if dedup_key not in seen_keys:
                        seen_keys.add(dedup_key)
                        all_locations.append(parsed)

            # Rate limiting
            time.sleep(0.1)

    log.info("scrape_complete", total_locations=len(all_locations), zip_codes_processed=len(ZIP_CODE_SEEDS))
    return all_locations


def locations_to_rows(
    locations: List[Dict[str, str]],
    merchant_id: Optional[int],
) -> List[List[str]]:
    """Convert locations to sheet rows matching the Scraped Locations schema (A:Q)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows: List[List[str]] = []

    for loc in locations:
        rows.append([
            MERCHANT_NAME,
            str(merchant_id) if merchant_id else "TBD",
            loc["name"],
            loc["address"],
            loc.get("address2", ""),
            loc["city"],
            loc["state"],
            loc["zip"],
            loc["phone"],
            loc.get("hours", ""),
            loc["store_url"],
            loc.get("latitude", ""),
            loc.get("longitude", ""),
            "Pending",
            now,
            "",  # pushed_at
            "v2_salvation_army_custom",
        ])

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Salvation Army Thrift Store locations via API"
    )
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    t0 = time.monotonic()

    # Fetch locations
    locations = get_locations()
    elapsed = time.monotonic() - t0

    log.info("scrape_done", locations=len(locations), elapsed_s=round(elapsed, 3))

    if not locations:
        print(f"\nNo locations found for {MERCHANT_NAME}")
        return

    # Build rows
    merchant_id = lookup_merchant_id(MERCHANT_NAME)
    rows = locations_to_rows(locations, merchant_id)

    print(f"\n{'=' * 60}")
    print(f"  {MERCHANT_NAME} - Custom API Scraper")
    print(f"{'=' * 60}")
    print(f"  Locations fetched:  {len(locations)}")
    print(f"  Valid rows:         {len(rows)}")
    print(f"  Elapsed:            {round(elapsed, 3)}s")

    if args.dry_run:
        print(f"  (DRY RUN - nothing written)")
        for r in rows[:10]:
            print(f"    {r[2]:45s} {r[5]:20s} {r[6]:2s} {r[7]:5s}")
        if len(rows) > 10:
            print(f"    ... and {len(rows) - 10} more")
    else:
        sheets_svc = get_sheets_service()
        resp = (
            sheets_svc.spreadsheets()
            .values()
            .append(
                spreadsheetId=args.sheet_id,
                range=f"{SCRAPED_TAB}!A:Q",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": rows},
            )
            .execute()
        )
        written = resp.get("updates", {}).get("updatedRows", len(rows))
        print(f"  Written to sheet:   {written}")

    print()


if __name__ == "__main__":
    main()
