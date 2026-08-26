"""Create the 'Saverwell Subscribe Queue Processor' n8n workflow.

Replaces the webhook-based subscribe flow with a DB queue approach:
  - Edge function writes to subscribe_queue table (no Cloudflare bypass needed)
  - This workflow polls every 60s, processes pending rows, marks done
  - Same downstream pipeline: Google Sheet, Supabase signups, Customer.io, GA4

Usage:
    python scripts/create_subscribe_queue_workflow.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

# Supabase credentials for queue read/write (HTTP Request nodes)
SUPABASE_URL = "https://lmtrgkmgfermqatopkfp.supabase.co"
SUPABASE_SERVICE_KEY = os.environ.get(
    "SUPABASE_SERVICE_ROLE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxtdHJna21nZmVybXFhdG9wa2ZwIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NTk3NzA1NCwiZXhwIjoyMDgxNTUzMDU0fQ.R2zvCHiUgfwnp2Q096UPYNurTlPgMHcbAOyBGIS-ozQ",
)

# ZIP-to-state lookup (same as existing lifecycle workflow)
ZIP_TO_STATE_JS = """
const ZIP_TO_STATE = {
  '005':'NY','006':'PR','007':'PR','008':'PR','009':'PR',
  '010':'MA','011':'MA','012':'MA','013':'MA','014':'MA','015':'MA','016':'MA','017':'MA','018':'MA','019':'MA',
  '020':'MA','021':'MA','022':'MA','023':'MA','024':'MA','025':'MA','026':'MA','027':'MA',
  '028':'RI','029':'RI',
  '030':'NH','031':'NH','032':'NH','033':'NH','034':'NH','035':'NH','036':'NH','037':'NH','038':'NH',
  '039':'ME',
  '040':'ME','041':'ME','042':'ME','043':'ME','044':'ME','045':'ME','046':'ME','047':'ME','048':'ME','049':'ME',
  '050':'VT','051':'VT','052':'VT','053':'VT','054':'VT','055':'VT','056':'VT','057':'VT','058':'VT','059':'VT',
  '060':'CT','061':'CT','062':'CT','063':'CT','064':'CT','065':'CT','066':'CT','067':'CT','068':'CT','069':'CT',
  '070':'NJ','071':'NJ','072':'NJ','073':'NJ','074':'NJ','075':'NJ','076':'NJ','077':'NJ','078':'NJ','079':'NJ',
  '080':'NJ','081':'NJ','082':'NJ','083':'NJ','084':'NJ','085':'NJ','086':'NJ','087':'NJ','088':'NJ','089':'NJ',
  '100':'NY','101':'NY','102':'NY','103':'NY','104':'NY','105':'NY','106':'NY','107':'NY','108':'NY','109':'NY',
  '110':'NY','111':'NY','112':'NY','113':'NY','114':'NY','115':'NY','116':'NY','117':'NY','118':'NY','119':'NY',
  '120':'NY','121':'NY','122':'NY','123':'NY','124':'NY','125':'NY','126':'NY','127':'NY','128':'NY','129':'NY',
  '130':'NY','131':'NY','132':'NY','133':'NY','134':'NY','135':'NY','136':'NY','137':'NY','138':'NY','139':'NY',
  '140':'NY','141':'NY','142':'NY','143':'NY','144':'NY','145':'NY','146':'NY','147':'NY','148':'NY','149':'NY',
  '150':'PA','151':'PA','152':'PA','153':'PA','154':'PA','155':'PA','156':'PA','157':'PA','158':'PA','159':'PA',
  '160':'PA','161':'PA','162':'PA','163':'PA','164':'PA','165':'PA','166':'PA','167':'PA','168':'PA','169':'PA',
  '170':'PA','171':'PA','172':'PA','173':'PA','174':'PA','175':'PA','176':'PA','177':'PA','178':'PA','179':'PA',
  '180':'PA','181':'PA','182':'PA','183':'PA','184':'PA','185':'PA','186':'PA','187':'PA','188':'PA','189':'PA',
  '190':'PA','191':'PA','192':'PA','193':'PA','194':'PA','195':'PA','196':'PA',
  '197':'DE','198':'DE','199':'DE',
  '200':'DC','201':'VA','202':'DC','203':'DC','204':'DC','205':'DC',
  '206':'MD','207':'MD','208':'MD','209':'MD','210':'MD','211':'MD','212':'MD','214':'MD','215':'MD','216':'MD',
  '217':'WV','218':'WV',
  '220':'VA','221':'VA','222':'VA','223':'VA','224':'VA','225':'VA','226':'VA','227':'VA','228':'VA','229':'VA',
  '230':'VA','231':'VA','232':'VA','233':'VA','234':'VA','235':'VA','236':'VA','237':'VA','238':'VA','239':'VA',
  '240':'VA','241':'VA','242':'VA','243':'VA','244':'VA','245':'VA','246':'VA','247':'WV','248':'WV','249':'WV',
  '250':'WV','251':'WV','252':'WV','253':'WV','254':'WV','255':'WV','256':'WV','257':'WV','258':'WV','259':'WV',
  '260':'WV','261':'WV','262':'WV','263':'WV','264':'WV','265':'WV','266':'WV','267':'WV','268':'WV',
  '270':'NC','271':'NC','272':'NC','273':'NC','274':'NC','275':'NC','276':'NC','277':'NC','278':'NC','279':'NC',
  '280':'NC','281':'NC','282':'NC','283':'NC','284':'NC','285':'NC','286':'NC','287':'NC','288':'NC','289':'NC',
  '290':'SC','291':'SC','292':'SC','293':'SC','294':'SC','295':'SC','296':'SC','297':'SC','298':'SC','299':'SC',
  '300':'GA','301':'GA','302':'GA','303':'GA','304':'GA','305':'GA','306':'GA','307':'GA','308':'GA','309':'GA',
  '310':'GA','311':'GA','312':'GA','313':'GA','314':'GA','315':'GA','316':'GA','317':'GA','318':'GA','319':'GA',
  '320':'FL','321':'FL','322':'FL','323':'FL','324':'FL','325':'FL','326':'FL','327':'FL','328':'FL','329':'FL',
  '330':'FL','331':'FL','332':'FL','333':'FL','334':'FL','335':'FL','336':'FL','337':'FL','338':'FL','339':'FL',
  '340':'AA','341':'FL','342':'FL','344':'FL','346':'FL','347':'FL','349':'FL',
  '350':'AL','351':'AL','352':'AL','353':'AL','354':'AL','355':'AL','356':'AL','357':'AL','358':'AL','359':'AL',
  '360':'AL','361':'AL','362':'AL','363':'AL','364':'AL','365':'AL','366':'AL','367':'AL','368':'AL','369':'MS',
  '370':'TN','371':'TN','372':'TN','373':'TN','374':'TN','375':'TN','376':'TN','377':'TN','378':'TN','379':'TN',
  '380':'TN','381':'TN','382':'TN','383':'TN','384':'TN','385':'TN',
  '386':'MS','387':'MS','388':'MS','389':'MS','390':'MS','391':'MS','392':'MS','393':'MS','394':'MS','395':'MS',
  '396':'MS','397':'MS',
  '400':'KY','401':'KY','402':'KY','403':'KY','404':'KY','405':'KY','406':'KY','407':'KY','408':'KY','409':'KY',
  '410':'KY','411':'KY','412':'KY','413':'KY','414':'KY','415':'KY','416':'KY','417':'KY','418':'KY',
  '420':'KY','421':'KY','422':'KY','423':'KY','424':'KY','425':'KY','426':'KY','427':'KY',
  '430':'OH','431':'OH','432':'OH','433':'OH','434':'OH','435':'OH','436':'OH','437':'OH','438':'OH','439':'OH',
  '440':'OH','441':'OH','442':'OH','443':'OH','444':'OH','445':'OH','446':'OH','447':'OH','448':'OH','449':'OH',
  '450':'OH','451':'OH','452':'OH','453':'OH','454':'OH','455':'OH','456':'OH','457':'OH','458':'OH',
  '460':'IN','461':'IN','462':'IN','463':'IN','464':'IN','465':'IN','466':'IN','467':'IN','468':'IN','469':'IN',
  '470':'IN','471':'IN','472':'IN','473':'IN','474':'IN','475':'IN','476':'IN','477':'IN','478':'IN','479':'IN',
  '480':'MI','481':'MI','482':'MI','483':'MI','484':'MI','485':'MI','486':'MI','487':'MI','488':'MI','489':'MI',
  '490':'MI','491':'MI','492':'MI','493':'MI','494':'MI','495':'MI','496':'MI','497':'MI','498':'MI','499':'MI',
  '500':'IA','501':'IA','502':'IA','503':'IA','504':'IA','505':'IA','506':'IA','507':'IA','508':'IA','509':'IA',
  '510':'IA','511':'IA','512':'IA','513':'IA','514':'IA','515':'IA','516':'IA','520':'IA','521':'IA','522':'IA',
  '523':'IA','524':'IA','525':'IA','526':'IA','527':'IA','528':'IA',
  '530':'WI','531':'WI','532':'WI','534':'WI','535':'WI','537':'WI','538':'WI','539':'WI',
  '540':'WI','541':'WI','542':'WI','543':'WI','544':'WI','545':'WI','546':'WI','547':'WI','548':'WI','549':'WI',
  '550':'MN','551':'MN','553':'MN','554':'MN','555':'MN','556':'MN','557':'MN','558':'MN','559':'MN',
  '560':'MN','561':'MN','562':'MN','563':'MN','564':'MN','565':'MN','566':'MN','567':'MN',
  '570':'SD','571':'SD','572':'SD','573':'SD','574':'SD','575':'SD','576':'SD','577':'SD',
  '580':'ND','581':'ND','582':'ND','583':'ND','584':'ND','585':'ND','586':'ND','587':'ND','588':'ND',
  '590':'MT','591':'MT','592':'MT','593':'MT','594':'MT','595':'MT','596':'MT','597':'MT','598':'MT','599':'MT',
  '600':'IL','601':'IL','602':'IL','603':'IL','604':'IL','605':'IL','606':'IL','607':'IL','608':'IL','609':'IL',
  '610':'IL','611':'IL','612':'IL','613':'IL','614':'IL','615':'IL','616':'IL','617':'IL','618':'IL','619':'IL',
  '620':'IL','621':'IL','622':'IL','623':'IL','624':'IL','625':'IL','626':'IL','627':'IL','628':'IL','629':'IL',
  '630':'MO','631':'MO','633':'MO','634':'MO','635':'MO','636':'MO','637':'MO','638':'MO','639':'MO',
  '640':'MO','641':'MO','644':'MO','645':'MO','646':'MO','647':'MO','648':'MO','649':'MO',
  '650':'MO','651':'MO','652':'MO','653':'MO','654':'MO','655':'MO','656':'MO','657':'MO','658':'MO','659':'MO',
  '660':'KS','661':'KS','662':'KS','664':'KS','665':'KS','666':'KS','667':'KS','668':'KS','669':'KS',
  '670':'KS','671':'KS','672':'KS','673':'KS','674':'KS','675':'KS','676':'KS','677':'KS','678':'KS','679':'KS',
  '680':'NE','681':'NE','683':'NE','684':'NE','685':'NE','686':'NE','687':'NE','688':'NE','689':'NE','690':'NE',
  '691':'NE','692':'NE','693':'NE',
  '700':'LA','701':'LA','703':'LA','704':'LA','705':'LA','706':'LA','707':'LA','708':'LA',
  '710':'LA','711':'LA','712':'LA','713':'LA','714':'LA',
  '716':'AR','717':'AR','718':'AR','719':'AR','720':'AR','721':'AR','722':'AR','723':'AR','724':'AR','725':'AR',
  '726':'AR','727':'AR','728':'AR','729':'AR',
  '730':'OK','731':'OK','734':'OK','735':'OK','736':'OK','737':'OK','738':'OK','739':'OK',
  '740':'OK','741':'OK','743':'OK','744':'OK','745':'OK','746':'OK','747':'OK','748':'OK','749':'OK',
  '750':'TX','751':'TX','752':'TX','753':'TX','754':'TX','755':'TX','756':'TX','757':'TX','758':'TX','759':'TX',
  '760':'TX','761':'TX','762':'TX','763':'TX','764':'TX','765':'TX','766':'TX','767':'TX','768':'TX','769':'TX',
  '770':'TX','771':'TX','772':'TX','773':'TX','774':'TX','775':'TX','776':'TX','777':'TX','778':'TX','779':'TX',
  '780':'TX','781':'TX','782':'TX','783':'TX','784':'TX','785':'TX','786':'TX','787':'TX','788':'TX','789':'TX',
  '790':'TX','791':'TX','792':'TX','793':'TX','794':'TX','795':'TX','796':'TX','797':'TX','798':'TX','799':'TX',
  '800':'CO','801':'CO','802':'CO','803':'CO','804':'CO','805':'CO','806':'CO','807':'CO','808':'CO','809':'CO',
  '810':'CO','811':'CO','812':'CO','813':'CO','814':'CO','815':'CO','816':'CO',
  '820':'WY','821':'WY','822':'WY','823':'WY','824':'WY','825':'WY','826':'WY','827':'WY','828':'WY','829':'WY',
  '830':'WY','831':'WY',
  '832':'ID','833':'ID','834':'ID','835':'ID','836':'ID','837':'ID','838':'ID',
  '840':'UT','841':'UT','842':'UT','843':'UT','844':'UT','845':'UT','846':'UT','847':'UT',
  '850':'AZ','851':'AZ','852':'AZ','853':'AZ','855':'AZ','856':'AZ','857':'AZ','859':'AZ',
  '860':'AZ','863':'AZ','864':'AZ','865':'AZ',
  '870':'NM','871':'NM','872':'NM','873':'NM','874':'NM','875':'NM','877':'NM','878':'NM','879':'NM',
  '880':'TX','881':'TX','882':'TX','883':'TX','884':'TX','885':'NM',
  '889':'NV','890':'NV','891':'NV','893':'NV','894':'NV','895':'NV','897':'NV','898':'NV',
  '900':'CA','901':'CA','902':'CA','903':'CA','904':'CA','905':'CA','906':'CA','907':'CA','908':'CA','909':'CA',
  '910':'CA','911':'CA','912':'CA','913':'CA','914':'CA','915':'CA','916':'CA','917':'CA','918':'CA','919':'CA',
  '920':'CA','921':'CA','922':'CA','923':'CA','924':'CA','925':'CA','926':'CA','927':'CA','928':'CA',
  '930':'CA','931':'CA','932':'CA','933':'CA','934':'CA','935':'CA','936':'CA','937':'CA','938':'CA','939':'CA',
  '940':'CA','941':'CA','942':'CA','943':'CA','944':'CA','945':'CA','946':'CA','947':'CA','948':'CA','949':'CA',
  '950':'CA','951':'CA','952':'CA','953':'CA','954':'CA','955':'CA','956':'CA','957':'CA','958':'CA','959':'CA',
  '960':'CA','961':'CA',
  '967':'HI','968':'HI',
  '970':'OR','971':'OR','972':'OR','973':'OR','974':'OR','975':'OR','976':'OR','977':'OR','978':'OR','979':'OR',
  '980':'WA','981':'WA','982':'WA','983':'WA','984':'WA','985':'WA','986':'WA','988':'WA','989':'WA',
  '990':'WA','991':'WA','992':'WA','993':'WA','994':'WA',
  '995':'AK','996':'AK','997':'AK','998':'AK','999':'AK'
};
"""

# Code node: extract payload from queue row and compute lifecycle attributes
PROCESS_COMPUTE_JS = (
    """// Extract payload from subscribe_queue row and compute lifecycle attributes
const items = $input.all();
const results = [];

"""
    + ZIP_TO_STATE_JS
    + """
for (const item of items) {
  const row = item.json;
  const p = row.payload || {};
  const email = p.email || '';
  const url = p.url || '';
  const zip = p.utm_zip_code || p.zip || '';

  // content_interest from signup page URL
  let content_interest = 'all';
  if (url.includes('/protection')) content_interest = 'protection';
  else if (url.includes('/guide') || url.includes('/medicare')) content_interest = 'guides';
  else if (url.includes('/discount') || url.includes('/savings')) content_interest = 'savings';

  // state from ZIP prefix
  let state_resolved = '';
  if (zip && zip.length >= 3) {
    state_resolved = ZIP_TO_STATE[zip.substring(0, 3)] || '';
  }

  results.push({
    json: {
      // Queue metadata
      queueId: row.id,
      // Sheet columns
      timestamp: p.timestamp || row.created_at,
      ip_address: p.ip_address || '',
      email: email,
      utm_source: p.utm_source || '',
      utm_campaign: p.utm_campaign || '',
      utm_content: p.utm_content || '',
      utm_medium: p.utm_medium || '',
      utm_referrer: p.utm_referrer || '',
      referring_url: p.referrer || '',
      utm_leadid: p.utm_leadid || '',
      utm_subid: p.utm_subid || '',
      utm_zip_code: zip,
      brand: p.brand || 'saverwell',
      full_json: JSON.stringify(p),
      content_interest: content_interest,
      state_resolved: state_resolved,
      lifecycle_stage: 'new',
      // Additional fields for signups + CIO
      source: p.source || 'site',
      consent: p.consent || '',
      site: p.site || '',
      url: url,
      referrer: p.referrer || '',
      company: p.company || '',
      welcome_flow_started: false,
      articles_received: 0,
      articles_received_list: '',
    }
  });
}

return results;
"""
)

# Code node: build Customer.io identify + track payloads
BUILD_CIO_JS = """// Build Customer.io Track API payloads
const item = $input.item.json;
const email = item.email || '';

// Use email as Customer.io identifier
const customerId = email;

// Parse timestamp to Unix seconds
let createdAt = Math.floor(Date.now() / 1000);
if (item.timestamp) {
  const parsed = new Date(item.timestamp).getTime();
  if (!isNaN(parsed)) createdAt = Math.floor(parsed / 1000);
}

const attributes = {
  email: email,
  created_at: createdAt,
  ip_address: item.ip_address || '',
  brand: item.brand || '',
  consent: item.consent || '',
  site: item.site || '',
  url: item.url || '',
  referrer: item.referrer || '',
  utm_source: item.utm_source || '',
  utm_campaign: item.utm_campaign || '',
  utm_medium: item.utm_medium || '',
  utm_content: item.utm_content || '',
  utm_referrer: item.utm_referrer || '',
  state: '',
  zip_code: item.utm_zip_code || '',
  leadid: item.utm_leadid || '',
  subid: item.utm_subid || '',
  company: item.company || '',
  content_interest: item.content_interest || 'all',
  state_resolved: item.state_resolved || '',
  lifecycle_stage: item.lifecycle_stage || 'new',
  welcome_flow_started: Boolean(item.welcome_flow_started),
  articles_received: parseInt(item.articles_received) || 0,
  articles_received_list: item.articles_received_list || ''
};

return {
  json: {
    ...item,
    customerId: customerId,
    identifyBody: attributes,
    eventBody: { name: 'email_subscribe' }
  },
  pairedItem: 0
};
"""

# Code node: build GA4 Measurement Protocol payload
BUILD_GA4_JS = """// Pure-JS SHA-256 (no require needed - n8n sandbox safe)
function sha256(msg) {
  function rr(v, a) { return (v >>> a) | (v << (32 - a)); }
  const K = [
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
  ];
  let H = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
  const bytes = [];
  for (let i = 0; i < msg.length; i++) bytes.push(msg.charCodeAt(i));
  bytes.push(0x80);
  while (bytes.length % 64 !== 56) bytes.push(0);
  const bitLen = msg.length * 8;
  for (let i = 56; i >= 0; i -= 8) bytes.push(i >= 32 ? 0 : (bitLen >>> i) & 0xff);
  for (let off = 0; off < bytes.length; off += 64) {
    const w = new Array(64);
    for (let i = 0; i < 16; i++) w[i] = (bytes[off+i*4]<<24)|(bytes[off+i*4+1]<<16)|(bytes[off+i*4+2]<<8)|bytes[off+i*4+3];
    for (let i = 16; i < 64; i++) {
      const s0 = rr(w[i-15],7) ^ rr(w[i-15],18) ^ (w[i-15]>>>3);
      const s1 = rr(w[i-2],17) ^ rr(w[i-2],19) ^ (w[i-2]>>>2);
      w[i] = (w[i-16] + s0 + w[i-7] + s1) | 0;
    }
    let [a,b,c,d,e,f,g,h] = H;
    for (let i = 0; i < 64; i++) {
      const S1 = rr(e,6) ^ rr(e,11) ^ rr(e,25);
      const ch = (e & f) ^ (~e & g);
      const t1 = (h + S1 + ch + K[i] + w[i]) | 0;
      const S0 = rr(a,2) ^ rr(a,13) ^ rr(a,22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (S0 + maj) | 0;
      h=g; g=f; f=e; e=(d+t1)|0; d=c; c=b; b=a; a=(t1+t2)|0;
    }
    H = [H[0]+a|0, H[1]+b|0, H[2]+c|0, H[3]+d|0, H[4]+e|0, H[5]+f|0, H[6]+g|0, H[7]+h|0];
  }
  return H.map(v => ('00000000'+(v>>>0).toString(16)).slice(-8)).join('');
}

const item = $input.item.json;
const email = (item.email || '').toLowerCase().trim();
const hashedEmail = sha256(email);

let signup_source = 'homepage';
const url = item.url || '';
if (url.includes('/protect')) signup_source = 'protection';
else if (url.includes('/guide') || url.includes('/medicare')) signup_source = 'guides';
else if (url.includes('/retailer')) signup_source = 'merchant';
else if (url.includes('/dma')) signup_source = 'dma';

const payload = {
  client_id: hashedEmail,
  user_id: hashedEmail,
  events: [{
    name: 'email_signup',
    params: {
      signup_source: signup_source,
      zip_code: item.utm_zip_code || '',
      content_interest: item.content_interest || 'all',
      engagement_time_msec: 1,
      utm_source: item.utm_source || '',
      utm_medium: item.utm_medium || '',
      utm_campaign: item.utm_campaign || ''
    }
  }],
  user_properties: {
    user_type: { value: 'subscriber' }
  }
};

return [{ json: { ...item, ga4Payload: payload }, pairedItem: 0 }];
"""


async def main() -> None:
    from cmo_agent.config import get_settings
    from cmo_agent.n8n.client import N8NClient

    settings = get_settings()
    client = N8NClient(
        base_url=settings.n8n_base_url,
        api_key=settings.n8n_api_key,
        timeout=settings.n8n_timeout,
    )

    async with client:
        workflow_payload = {
            "name": "Saverwell Subscribe Queue Processor",
            "nodes": [
                # 1. Schedule Trigger - every 1 minute
                {
                    "name": "Every 1 Minute",
                    "type": "n8n-nodes-base.scheduleTrigger",
                    "typeVersion": 1.2,
                    "position": [250, 300],
                    "parameters": {
                        "rule": {
                            "interval": [
                                {"field": "minutes", "minutesInterval": 1}
                            ]
                        }
                    },
                },
                # 2. Read Queue - GET pending rows from subscribe_queue
                {
                    "name": "Read Queue",
                    "type": "n8n-nodes-base.httpRequest",
                    "typeVersion": 4.2,
                    "position": [470, 300],
                    "parameters": {
                        "method": "GET",
                        "url": f"{SUPABASE_URL}/rest/v1/subscribe_queue?status=eq.pending&order=created_at.asc&limit=10",
                        "sendHeaders": True,
                        "headerParameters": {
                            "parameters": [
                                {
                                    "name": "apikey",
                                    "value": SUPABASE_SERVICE_KEY,
                                },
                                {
                                    "name": "Authorization",
                                    "value": f"Bearer {SUPABASE_SERVICE_KEY}",
                                },
                            ]
                        },
                        "options": {
                            "response": {
                                "response": {"responseFormat": "json"}
                            }
                        },
                    },
                },
                # 3. Process & Compute - extract payload, compute lifecycle
                {
                    "name": "Process & Compute",
                    "type": "n8n-nodes-base.code",
                    "typeVersion": 2.0,
                    "position": [690, 300],
                    "parameters": {"jsCode": PROCESS_COMPUTE_JS},
                },
                # 4. Append to Google Sheet
                {
                    "name": "Append to Sheet",
                    "type": "n8n-nodes-base.googleSheets",
                    "typeVersion": 4.7,
                    "position": [910, 300],
                    "parameters": {
                        "authentication": "serviceAccount",
                        "operation": "append",
                        "documentId": {
                            "__rl": True,
                            "value": "1doEALOLNSfYMw-QP7qPwyJlfj8L2Jv63EzZmKCDJ4YY",
                            "mode": "list",
                            "cachedResultName": "Saverwell Inquiries",
                            "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1doEALOLNSfYMw-QP7qPwyJlfj8L2Jv63EzZmKCDJ4YY/edit?usp=drivesdk",
                        },
                        "sheetName": {
                            "__rl": True,
                            "value": 1635517307,
                            "mode": "list",
                            "cachedResultName": "Subsribe",
                            "cachedResultUrl": "https://docs.google.com/spreadsheets/d/1doEALOLNSfYMw-QP7qPwyJlfj8L2Jv63EzZmKCDJ4YY/edit#gid=1635517307",
                        },
                        "columns": {
                            "mappingMode": "defineBelow",
                            "value": {
                                "timestamp": "={{ $json.timestamp }}",
                                "ip_address": "={{ $json.ip_address }}",
                                "email": "={{ $json.email }}",
                                "utm_source": "={{ $json.utm_source }}",
                                "utm_campaign": "={{ $json.utm_campaign }}",
                                "utm_content": "={{ $json.utm_content }}",
                                "utm_medium": "={{ $json.utm_medium }}",
                                "utm_referrer": "={{ $json.utm_referrer }}",
                                "referring_url": "={{ $json.referring_url }}",
                                "utm_leadid": "={{ $json.utm_leadid }}",
                                "utm_subid": "={{ $json.utm_subid }}",
                                "utm_zip_code": "={{ $json.utm_zip_code }}",
                                "brand": "={{ $json.brand }}",
                                "full_json": "={{ $json.full_json }}",
                                "content_interest": "={{ $json.content_interest }}",
                                "state_resolved": "={{ $json.state_resolved }}",
                                "lifecycle_stage": "={{ $json.lifecycle_stage }}",
                            },
                            "matchingColumns": [],
                            "schema": [
                                {"id": "timestamp", "displayName": "timestamp", "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                                {"id": "ip_address", "displayName": "ip_address", "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                                {"id": "email", "displayName": "email", "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                                {"id": "utm_source", "displayName": "utm_source", "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                                {"id": "utm_campaign", "displayName": "utm_campaign", "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                                {"id": "utm_content", "displayName": "utm_content", "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                                {"id": "utm_medium", "displayName": "utm_medium", "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                                {"id": "utm_referrer", "displayName": "utm_referrer", "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                                {"id": "referring_url", "displayName": "referring_url", "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                                {"id": "utm_leadid", "displayName": "utm_leadid", "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                                {"id": "utm_subid", "displayName": "utm_subid", "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                                {"id": "utm_zip_code", "displayName": "utm_zip_code", "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                                {"id": "brand", "displayName": "brand", "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                                {"id": "full_json", "displayName": "full_json", "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                                {"id": "content_interest", "displayName": "content_interest", "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                                {"id": "state_resolved", "displayName": "state_resolved", "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                                {"id": "lifecycle_stage", "displayName": "lifecycle_stage", "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                            ],
                            "attemptToConvertTypes": False,
                            "convertFieldsToString": False,
                        },
                        "options": {},
                    },
                    "credentials": {
                        "googleApi": {
                            "id": "C171OKcEU5uu568B",
                            "name": "Google Service Account account",
                        }
                    },
                },
                # 5. Insert into Supabase signups
                {
                    "name": "Insert Signup",
                    "type": "n8n-nodes-base.supabase",
                    "typeVersion": 1.0,
                    "position": [1130, 300],
                    "parameters": {
                        "tableId": "signups",
                        "fieldsUi": {
                            "fieldValues": [
                                {"fieldId": "created_at", "fieldValue": "={{ $json.timestamp }}"},
                                {"fieldId": "signup_type", "fieldValue": "subscribe"},
                                {"fieldId": "brand", "fieldValue": "={{ $json.brand }}"},
                                {"fieldId": "consent", "fieldValue": "={{ $json.consent }}"},
                                {"fieldId": "source", "fieldValue": "={{ $json.source }}"},
                                {"fieldId": "site", "fieldValue": "={{ $json.site }}"},
                                {"fieldId": "url", "fieldValue": "={{ $json.url }}"},
                                {"fieldId": "referrer", "fieldValue": "={{ $json.referrer }}"},
                                {"fieldId": "utm_source", "fieldValue": "={{ $json.utm_source }}"},
                                {"fieldId": "utm_campaign", "fieldValue": "={{ $json.utm_campaign }}"},
                                {"fieldId": "utm_medium", "fieldValue": "={{ $json.utm_medium }}"},
                                {"fieldId": "utm_content", "fieldValue": "={{ $json.utm_content }}"},
                                {"fieldId": "utm_referrer", "fieldValue": "={{ $json.utm_referrer }}"},
                                {"fieldId": "utm_zip_code", "fieldValue": "={{ $json.utm_zip_code }}"},
                                {"fieldId": "utm_leadid", "fieldValue": "={{ $json.utm_leadid }}"},
                                {"fieldId": "utm_subid", "fieldValue": "={{ $json.utm_subid }}"},
                                {"fieldId": "company", "fieldValue": "={{ $json.company }}"},
                                {"fieldId": "email", "fieldValue": "={{ $json.email }}"},
                                {"fieldId": "ip_address", "fieldValue": "={{ $json.ip_address }}"},
                            ]
                        },
                    },
                    "credentials": {
                        "supabaseApi": {
                            "id": "SvYiHFnN6BeUIQYA",
                            "name": "Supabase account",
                        }
                    },
                },
                # 6. Build CIO Payload
                {
                    "name": "Build CIO Payload",
                    "type": "n8n-nodes-base.code",
                    "typeVersion": 2.0,
                    "position": [1350, 300],
                    "parameters": {"jsCode": BUILD_CIO_JS},
                },
                # 7. Identify Customer in Customer.io
                {
                    "name": "Identify Customer",
                    "type": "n8n-nodes-base.httpRequest",
                    "typeVersion": 4.2,
                    "position": [1570, 300],
                    "parameters": {
                        "method": "PUT",
                        "url": "=https://track.customer.io/api/v1/customers/{{ encodeURIComponent($json.customerId) }}",
                        "authentication": "predefinedCredentialType",
                        "nodeCredentialType": "customerIoApi",
                        "sendBody": True,
                        "specifyBody": "json",
                        "jsonBody": "={{ JSON.stringify($json.identifyBody) }}",
                        "options": {},
                    },
                    "credentials": {
                        "customerIoApi": {
                            "id": "sLVSLHVPC7SJNotg",
                            "name": "Customer.io account",
                        }
                    },
                },
                # 8. Track Subscribe Event in Customer.io
                {
                    "name": "Track Subscribe Event",
                    "type": "n8n-nodes-base.httpRequest",
                    "typeVersion": 4.2,
                    "position": [1790, 300],
                    "parameters": {
                        "method": "POST",
                        "url": "=https://track.customer.io/api/v1/customers/{{ encodeURIComponent($('Build CIO Payload').item.json.customerId) }}/events",
                        "authentication": "predefinedCredentialType",
                        "nodeCredentialType": "customerIoApi",
                        "sendBody": True,
                        "specifyBody": "json",
                        "jsonBody": "={{ JSON.stringify($('Build CIO Payload').item.json.eventBody) }}",
                        "options": {},
                    },
                    "credentials": {
                        "customerIoApi": {
                            "id": "sLVSLHVPC7SJNotg",
                            "name": "Customer.io account",
                        }
                    },
                },
                # 9. Build GA4 Payload
                {
                    "name": "Build GA4 Payload",
                    "type": "n8n-nodes-base.code",
                    "typeVersion": 2.0,
                    "position": [2010, 300],
                    "parameters": {"jsCode": BUILD_GA4_JS},
                },
                # 10. Send to GA4
                {
                    "name": "Send to GA4",
                    "type": "n8n-nodes-base.httpRequest",
                    "typeVersion": 4.2,
                    "position": [2230, 300],
                    "parameters": {
                        "method": "POST",
                        "url": "https://www.google-analytics.com/mp/collect?measurement_id=G-YFGSQ1WTQM&api_secret=RGPelDOMT8CkqJPb22gkog",
                        "sendBody": True,
                        "specifyBody": "json",
                        "jsonBody": "={{ JSON.stringify($json.ga4Payload) }}",
                        "options": {"timeout": 5000},
                    },
                },
                # 11. Mark Queue Done
                {
                    "name": "Mark Queue Done",
                    "type": "n8n-nodes-base.httpRequest",
                    "typeVersion": 4.2,
                    "position": [2450, 300],
                    "parameters": {
                        "method": "PATCH",
                        "url": f"={SUPABASE_URL}/rest/v1/subscribe_queue?id=eq.{{{{ $('Process & Compute').item.json.queueId }}}}",
                        "sendHeaders": True,
                        "headerParameters": {
                            "parameters": [
                                {
                                    "name": "apikey",
                                    "value": SUPABASE_SERVICE_KEY,
                                },
                                {
                                    "name": "Authorization",
                                    "value": f"Bearer {SUPABASE_SERVICE_KEY}",
                                },
                                {
                                    "name": "Content-Type",
                                    "value": "application/json",
                                },
                                {
                                    "name": "Prefer",
                                    "value": "return=minimal",
                                },
                            ]
                        },
                        "sendBody": True,
                        "specifyBody": "json",
                        "jsonBody": '={"status": "done", "processed_at": "{{ $now }}"}',
                        "options": {},
                    },
                },
            ],
            "connections": {
                "Every 1 Minute": {
                    "main": [
                        [{"node": "Read Queue", "type": "main", "index": 0}]
                    ]
                },
                "Read Queue": {
                    "main": [
                        [{"node": "Process & Compute", "type": "main", "index": 0}]
                    ]
                },
                "Process & Compute": {
                    "main": [
                        [{"node": "Append to Sheet", "type": "main", "index": 0}]
                    ]
                },
                "Append to Sheet": {
                    "main": [
                        [{"node": "Insert Signup", "type": "main", "index": 0}]
                    ]
                },
                "Insert Signup": {
                    "main": [
                        [{"node": "Build CIO Payload", "type": "main", "index": 0}]
                    ]
                },
                "Build CIO Payload": {
                    "main": [
                        [{"node": "Identify Customer", "type": "main", "index": 0}]
                    ]
                },
                "Identify Customer": {
                    "main": [
                        [{"node": "Track Subscribe Event", "type": "main", "index": 0}]
                    ]
                },
                "Track Subscribe Event": {
                    "main": [
                        [{"node": "Build GA4 Payload", "type": "main", "index": 0}]
                    ]
                },
                "Build GA4 Payload": {
                    "main": [
                        [{"node": "Send to GA4", "type": "main", "index": 0}]
                    ]
                },
                "Send to GA4": {
                    "main": [
                        [{"node": "Mark Queue Done", "type": "main", "index": 0}]
                    ]
                },
            },
            "settings": {"executionOrder": "v1"},
        }

        print("Creating 'Saverwell Subscribe Queue Processor' workflow...")
        workflow = await client.create_workflow(workflow_payload)
        print(f"Workflow created!")
        print(f"  ID: {workflow.id}")
        print(f"  Name: {workflow.name}")
        print(f"  Active: {workflow.active}")
        print(f"  Nodes: {len(workflow.nodes)}")
        n8n_url = settings.n8n_base_url
        print(f"  URL: {n8n_url}/workflow/{workflow.id}")

        # Activate the workflow
        print("\nActivating workflow...")
        await client.activate_workflow(workflow.id)
        print("Workflow activated! Polling every 60 seconds.")


if __name__ == "__main__":
    asyncio.run(main())
