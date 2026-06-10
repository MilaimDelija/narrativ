"""
Prebunking Engine — proactive media literacy content generation
===============================================================

Generates prebunking material based on active narratives detected by the
Narrative Tracker and coordination signals from the CIB engine.

Prebunking (inoculation theory) is significantly more effective than
debunking: exposing manipulation *techniques* before they hit reduces
their impact. This engine generates:
  - Technique explainers (what manipulation tactic is being used)
  - Warning cards (what to watch for)
  - Verification guides (how to check this type of claim)

Languages: Albanian (sq), German (de), English (en)

The engine uses Groq API (Llama 3.3 70B) for content generation.
It never labels specific content as "false" — it describes manipulation
techniques without rendering a verdict on the underlying claims.

Author: Neuronium Engineers
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

# Groq API — optional import, graceful fallback to template mode
try:
    from groq import Groq
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False


# ── Data model ────────────────────────────────────────────────────────────

@dataclass
class PrebunkCard:
    card_id: str
    language: str               # "sq" | "de" | "en"
    technique: str              # name of detected manipulation technique
    headline: str               # short alert headline
    explanation: str            # what is this technique and why it works
    warning_signs: list[str]    # what to look for
    verification_guide: str     # how to check this type of claim
    source_atom_id: Optional[str] = None    # linked narrative atom
    generated_at: str = ""

    def as_dict(self) -> dict:
        return {
            "card_id": self.card_id,
            "language": self.language,
            "technique": self.technique,
            "headline": self.headline,
            "explanation": self.explanation,
            "warning_signs": self.warning_signs,
            "verification_guide": self.verification_guide,
            "source_atom_id": self.source_atom_id,
            "generated_at": self.generated_at,
        }


# ── Technique detection ───────────────────────────────────────────────────

def detect_techniques(cib_report: dict, tracker_report: dict) -> list[str]:
    """
    Infer which manipulation techniques are active based on engine signals.
    Returns a list of technique names for prebunking content generation.
    """
    techniques = []

    summary = cib_report.get("summary", {})
    clusters = cib_report.get("clusters", [])
    narratives = tracker_report.get("narratives", [])

    # Coordinated amplification ring
    if clusters and any(c.get("reciprocity", 0) >= 0.7 for c in clusters):
        techniques.append("coordinated_amplification")

    # Copy-paste campaign
    dup_pairs = summary.get("cross_account_duplicate_pairs", 0)
    if dup_pairs >= 10:
        techniques.append("copy_paste_campaign")

    # Astroturfing (many new accounts, same creation week)
    flagged = cib_report.get("flagged_accounts", [])
    if len(flagged) >= 5:
        high_meta = [a for a in flagged
                     if a.get("signals", {}).get("metadata", 0) >= 0.4]
        if len(high_meta) >= 3:
            techniques.append("astroturfing")

    # Velocity manipulation (fast-spreading narrative with CIB involvement)
    if narratives:
        fast = [n for n in narratives
                if n.get("spread", {}).get("velocity_accounts_per_hour", 0) > 20]
        if fast and flagged:
            techniques.append("velocity_manipulation")

    # Paid amplification (disclosed sponsored posts in dataset)
    # Detected by dashboard_export categories — if report has paid bucket
    # we surface the disclosure transparency technique
    techniques.append("source_transparency")   # always include

    return list(dict.fromkeys(techniques))   # deduplicate, preserve order


# ── Template fallback (no Groq API) ──────────────────────────────────────

_TEMPLATES: dict[str, dict[str, dict]] = {
    "coordinated_amplification": {
        "sq": {
            "headline": "Kujdes: Amplifikim i koordinuar i zbuluar",
            "explanation": (
                "Amplifikimi i koordinuar ndodh kur grupe llogarish postozin "
                "të njëjtin mesazh njëkohësisht për ta bërë atë të duket më "
                "popullor se sa është në të vërtetë. Kjo teknikë krijon "
                "iluzionin e konsensusit të gjerë."
            ),
            "warning_signs": [
                "Shumë llogari postozin mesazhin e njëjtë brenda minutave",
                "Llogaritë kanë pak ndjekës por ndajnë shumë",
                "Llogaritë janë krijuar afërsisht në të njëjtën kohë",
                "Teksti është pothuajse identik ndër postime të ndryshme"
            ],
            "verification_guide": (
                "Kontrollo datën e krijimit të llogarive që ndajnë mesazhin. "
                "Kërko nëse i njëjti tekst shfaqet njëkohësisht nga llogari "
                "të palidhura. Verifikoni burimin origjinal të pretendimit."
            ),
        },
        "de": {
            "headline": "Achtung: Koordinierte Verstärkung erkannt",
            "explanation": (
                "Koordinierte Verstärkung liegt vor, wenn Gruppen von Konten "
                "gleichzeitig dieselbe Botschaft posten, um sie populärer "
                "erscheinen zu lassen als sie ist. Diese Technik erzeugt "
                "die Illusion eines breiten Konsenses."
            ),
            "warning_signs": [
                "Viele Konten posten binnen Minuten dieselbe Nachricht",
                "Konten haben wenige Follower, teilen aber viel",
                "Konten wurden ungefähr zur gleichen Zeit erstellt",
                "Der Text ist in verschiedenen Posts nahezu identisch"
            ],
            "verification_guide": (
                "Prüfen Sie das Erstellungsdatum der Konten, die die Nachricht teilen. "
                "Suchen Sie, ob derselbe Text gleichzeitig von nicht verbundenen "
                "Konten erscheint. Überprüfen Sie die Originalquelle der Behauptung."
            ),
        },
        "en": {
            "headline": "Alert: Coordinated amplification detected",
            "explanation": (
                "Coordinated amplification occurs when groups of accounts post "
                "the same message simultaneously to make it appear more popular "
                "than it is. This technique creates an illusion of broad consensus."
            ),
            "warning_signs": [
                "Many accounts post identical content within minutes",
                "Accounts have few followers but share extensively",
                "Accounts were created at approximately the same time",
                "Text is nearly identical across different posts"
            ],
            "verification_guide": (
                "Check the creation date of accounts sharing the message. "
                "Search whether the same text appears simultaneously from "
                "unconnected accounts. Verify the original source of the claim."
            ),
        },
    },
    "copy_paste_campaign": {
        "sq": {
            "headline": "Fushatë kopje-ngjit e zbuluar",
            "explanation": (
                "Fushatat kopje-ngjit shpërndajnë mesazhe identike ose "
                "pothuajse identike nëpërmjet shumë llogarish. Kjo nuk është "
                "sjellje organike — njerëzit normalë shprehin idetë me fjalë "
                "të tyre. Teksti identik sugjeron koordinim të centralizuar."
            ),
            "warning_signs": [
                "I njëjti tekst fjalë për fjalë nga llogari të ndryshme",
                "Ndryshime minimale — një fjalë e ndryshuar ose hashtag shtesë",
                "Shpërndarje e papritshme dhe shumë e shpejtë e të njëjtit mesazh"
            ],
            "verification_guide": (
                "Kërko fragmentin e saktë të tekstit. Nëse rezultate identike "
                "shfaqen nga llogari të shumta njëkohësisht, kjo është shenjë "
                "e koordinimit. Gjej se ku u shfaq mesazhi fillimisht."
            ),
        },
        "de": {
            "headline": "Copy-Paste-Kampagne erkannt",
            "explanation": (
                "Copy-Paste-Kampagnen verbreiten identische oder nahezu identische "
                "Nachrichten über viele Konten. Dies ist kein organisches Verhalten — "
                "echte Menschen drücken Ideen mit eigenen Worten aus. "
                "Identischer Text deutet auf zentralisierte Koordination hin."
            ),
            "warning_signs": [
                "Wortgleicher Text von verschiedenen Konten",
                "Minimale Variationen — ein geändertes Wort oder zusätzlicher Hashtag",
                "Plötzliche und sehr schnelle Verbreitung derselben Nachricht"
            ],
            "verification_guide": (
                "Suchen Sie nach dem genauen Textfragment. Wenn identische Ergebnisse "
                "gleichzeitig von mehreren Konten erscheinen, ist das ein Zeichen von "
                "Koordination. Finden Sie heraus, wo die Nachricht zuerst erschien."
            ),
        },
        "en": {
            "headline": "Copy-paste campaign detected",
            "explanation": (
                "Copy-paste campaigns spread identical or near-identical messages "
                "across many accounts. This is not organic behaviour — real people "
                "express ideas in their own words. Identical text suggests "
                "centralised coordination."
            ),
            "warning_signs": [
                "Word-for-word identical text from different accounts",
                "Minimal variations — one changed word or extra hashtag",
                "Sudden and very rapid spread of the same message"
            ],
            "verification_guide": (
                "Search for the exact text fragment. If identical results appear "
                "from multiple accounts simultaneously, that is a sign of "
                "coordination. Find where the message first appeared."
            ),
        },
    },
    "astroturfing": {
        "sq": {
            "headline": "Astroturfing: lëvizje artificiale e dukjes organike",
            "explanation": (
                "Astroturfing krijon iluzionin e një lëvizjeje qytetare të "
                "vërtetë kur në realitet buron nga organizata ose individë "
                "të koordinuar. Emri vjen nga lendina artificiale — duket si "
                "bar i vërtetë por nuk është."
            ),
            "warning_signs": [
                "Shumë llogari të reja (krijuar muajt e fundit) mbrojnë të njëjtin qëndrim",
                "Llogaritë kanë profilet bosh ose minimale",
                "Aktiviteti rritet papritmas pastaj zhduket",
                "Llogaritë ndjekin njëra-tjetrën por askënd tjetër"
            ],
            "verification_guide": (
                "Kontrollo datën e krijimit dhe historikun e postimeve të llogarive. "
                "Vlerëso nëse aktiviteti filloi para apo pas ngjarjes që diskutohet. "
                "Kërko llogari reale me historik të gjatë dhe të larmishëm."
            ),
        },
        "de": {
            "headline": "Astroturfing: künstliche Graswurzelbewegung",
            "explanation": (
                "Astroturfing erzeugt die Illusion einer echten Bürgerbewegung, "
                "obwohl sie tatsächlich von koordinierten Organisationen oder "
                "Einzelpersonen stammt. Der Begriff kommt von Kunstgras — "
                "es sieht aus wie echtes Gras, ist aber keins."
            ),
            "warning_signs": [
                "Viele neue Konten (in den letzten Monaten erstellt) vertreten denselben Standpunkt",
                "Konten haben leere oder minimale Profile",
                "Aktivität steigt plötzlich an und verschwindet dann",
                "Konten folgen sich gegenseitig, aber sonst niemandem"
            ],
            "verification_guide": (
                "Überprüfen Sie Erstellungsdatum und Posting-Historie der Konten. "
                "Bewerten Sie, ob die Aktivität vor oder nach dem diskutierten Ereignis begann. "
                "Suchen Sie nach echten Konten mit langer, vielfältiger Geschichte."
            ),
        },
        "en": {
            "headline": "Astroturfing: fake grassroots movement",
            "explanation": (
                "Astroturfing creates the illusion of a genuine civic movement "
                "when it actually originates from coordinated organisations or "
                "individuals. The name comes from artificial turf — it looks "
                "like real grass but isn't."
            ),
            "warning_signs": [
                "Many new accounts (created in recent months) all advocate the same position",
                "Accounts have empty or minimal profiles",
                "Activity spikes suddenly then disappears",
                "Accounts follow each other but almost no one else"
            ],
            "verification_guide": (
                "Check the creation date and posting history of accounts. "
                "Assess whether activity began before or after the event being discussed. "
                "Look for real accounts with long, varied histories."
            ),
        },
    },
    "velocity_manipulation": {
        "sq": {
            "headline": "Manipulim i shpejtësisë: trending artificial",
            "explanation": (
                "Disa operacione ndikimi synojnë të bëjnë një temë 'trending' "
                "artificialisht duke e shpërndarë shumë shpejt brenda një "
                "dritareje të shkurtër kohore. Shpejtësia e lartë e shpërndarjes "
                "shfrytëzon algoritmet e platformave që shpërblejnë trending-ët."
            ),
            "warning_signs": [
                "Tema kalon nga zero në trending brenda minutave",
                "Shpërndarje ndodh kryesisht gjatë natës ose jashtë orareve normale",
                "Llogaritë kryesore të shpërndarjes kanë sjellje jo-organike",
                "Pas peaks-it fillestar, interesi bie menjëherë"
            ],
            "verification_guide": (
                "Shiko grafikun e shpërndarjes kohore të temës. "
                "Trending organike ka kthesa graduale; ajo artificiale ka "
                "spike të mprehtë. Kontrollo cilat llogari e filluan shpërndarjen."
            ),
        },
        "de": {
            "headline": "Geschwindigkeitsmanipulation: künstliches Trending",
            "explanation": (
                "Einige Einflussoperationen versuchen, ein Thema durch "
                "sehr schnelle Verbreitung innerhalb eines kurzen Zeitfensters "
                "künstlich trending zu machen. Die hohe Verbreitungsgeschwindigkeit "
                "nutzt Plattformalgorithmen aus, die Trends belohnen."
            ),
            "warning_signs": [
                "Thema geht innerhalb von Minuten von null auf trending",
                "Verbreitung findet hauptsächlich nachts oder außerhalb normaler Zeiten statt",
                "Hauptverbreitungskonten zeigen nicht-organisches Verhalten",
                "Nach dem ersten Peak fällt das Interesse sofort ab"
            ],
            "verification_guide": (
                "Schauen Sie sich das zeitliche Verbreitungsdiagramm des Themas an. "
                "Organisches Trending hat sanfte Kurven; künstliches hat steile Spitzen. "
                "Überprüfen Sie, welche Konten die Verbreitung starteten."
            ),
        },
        "en": {
            "headline": "Velocity manipulation: artificial trending",
            "explanation": (
                "Some influence operations aim to make a topic artificially trending "
                "by spreading it very rapidly within a short time window. High "
                "spread velocity exploits platform algorithms that reward trends."
            ),
            "warning_signs": [
                "Topic goes from zero to trending within minutes",
                "Spreading occurs mainly at night or outside normal hours",
                "Leading spreading accounts show non-organic behaviour",
                "After the initial spike, interest drops immediately"
            ],
            "verification_guide": (
                "Look at the temporal spread graph of the topic. "
                "Organic trending has gradual curves; artificial has sharp spikes. "
                "Check which accounts started the spreading."
            ),
        },
    },
    "source_transparency": {
        "sq": {
            "headline": "Si të identifikosh burimin e informacionit",
            "explanation": (
                "Çdo pjesë informacioni ka burim. Transparenca e burimit do "
                "të thotë të dimë kush e prodhuoi, kush e financoi dhe kush "
                "e shpërndan. Mungesa e transparencës nuk do të thotë "
                "detyrimisht dezinformatë — por kërkon verifikim shtesë."
            ),
            "warning_signs": [
                "Nuk ka burim të cituar ose lidha të vdekura",
                "Burimi origjinal është i panjohur ose i fshehur",
                "Informacioni shpërndahet nga llogari të anonim",
                "Financimi ose pronësia e medias nuk është e qartë"
            ],
            "verification_guide": (
                "Kërko burimin origjinal — jo ndajën e tretë. "
                "Kontrollo nëse media ka pronësi dhe financim transparent. "
                "Verifikoni me burime të pavarura para se të ndash."
            ),
        },
        "de": {
            "headline": "So erkennen Sie die Informationsquelle",
            "explanation": (
                "Jede Information hat eine Quelle. Quellentransparenz bedeutet "
                "zu wissen, wer sie produziert, wer sie finanziert und wer "
                "sie verbreitet hat. Mangelnde Transparenz bedeutet nicht "
                "unbedingt Desinformation — erfordert aber zusätzliche Prüfung."
            ),
            "warning_signs": [
                "Keine zitierte Quelle oder tote Links",
                "Originalquelle unbekannt oder verborgen",
                "Informationen werden von anonymen Konten geteilt",
                "Finanzierung oder Eigentümerschaft der Medien unklar"
            ],
            "verification_guide": (
                "Suchen Sie die Originalquelle — nicht den Drittteiler. "
                "Prüfen Sie, ob die Medien transparente Eigentümerschaft und "
                "Finanzierung haben. Verifizieren Sie mit unabhängigen Quellen, "
                "bevor Sie teilen."
            ),
        },
        "en": {
            "headline": "How to identify the source of information",
            "explanation": (
                "Every piece of information has a source. Source transparency "
                "means knowing who produced it, who funded it and who is "
                "spreading it. Lack of transparency does not necessarily mean "
                "disinformation — but it requires additional verification."
            ),
            "warning_signs": [
                "No cited source or dead links",
                "Original source unknown or hidden",
                "Information shared by anonymous accounts",
                "Funding or media ownership unclear"
            ],
            "verification_guide": (
                "Find the original source — not the third-party sharer. "
                "Check whether the media outlet has transparent ownership and "
                "funding. Verify with independent sources before sharing."
            ),
        },
    },
}


# ── Groq-powered generation ───────────────────────────────────────────────

_GROQ_SYSTEM = """You are a media literacy expert generating prebunking content.
You explain manipulation techniques WITHOUT judging the underlying claims.
You never say content is "false" or "true" — you describe HOW a technique works.
Respond ONLY with valid JSON matching the schema provided.
Do not include markdown fences or any text outside the JSON object."""

_GROQ_PROMPT = """Generate a prebunking card for the manipulation technique: "{technique}"

Context from detected data:
{context}

Language: {language_name} (ISO code: {lang})

Return exactly this JSON schema:
{{
  "headline": "short alert headline (max 80 chars)",
  "explanation": "2-3 sentence explanation of this technique and why it works psychologically",
  "warning_signs": ["sign 1", "sign 2", "sign 3", "sign 4"],
  "verification_guide": "2-3 sentence guide on how to check this type of claim"
}}"""

_LANG_NAMES = {"sq": "Albanian", "de": "German", "en": "English"}


def _generate_with_groq(technique: str, lang: str, context: str,
                         api_key: str) -> Optional[dict]:
    if not _GROQ_AVAILABLE:
        return None
    try:
        client = Groq(api_key=api_key)
        prompt = _GROQ_PROMPT.format(
            technique=technique.replace("_", " "),
            context=context[:500],
            language_name=_LANG_NAMES.get(lang, lang),
            lang=lang,
        )
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": _GROQ_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=600,
            temperature=0.4,
        )
        raw = resp.choices[0].message.content.strip()
        # Strip markdown fences if model adds them anyway
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception:
        return None


# ── Main engine ───────────────────────────────────────────────────────────

class PrebunkingEngine:
    def __init__(self, languages: list[str] = None, groq_api_key: Optional[str] = None):
        self.languages = languages or ["sq", "en", "de"]
        self.api_key = groq_api_key or os.getenv("GROQ_API_KEY")

    def generate(self,
                 cib_report: dict,
                 tracker_report: dict,
                 atom_id: Optional[str] = None) -> dict:
        """
        Generate prebunking cards for all detected techniques.
        Optionally link to a specific narrative atom.
        """
        techniques = detect_techniques(cib_report, tracker_report)
        context = self._build_context(cib_report, tracker_report)

        cards: list[dict] = []
        for tech in techniques:
            for lang in self.languages:
                card = self._make_card(tech, lang, context, atom_id)
                cards.append(card.as_dict())

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "techniques_detected": techniques,
            "languages": self.languages,
            "total_cards": len(cards),
            "cards": cards,
            "methodology_note": (
                "These cards describe manipulation techniques, not claims. "
                "No content is labelled true or false. Cards are intended for "
                "human media literacy educators and citizens."
            ),
        }

    def _make_card(self, technique: str, lang: str, context: str,
                   atom_id: Optional[str]) -> PrebunkCard:
        card_id = f"pb_{technique}_{lang}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        # Try Groq first, fall back to template
        generated = None
        if self.api_key:
            generated = _generate_with_groq(technique, lang, context, self.api_key)

        if generated:
            return PrebunkCard(
                card_id=card_id,
                language=lang,
                technique=technique,
                headline=generated.get("headline", ""),
                explanation=generated.get("explanation", ""),
                warning_signs=generated.get("warning_signs", []),
                verification_guide=generated.get("verification_guide", ""),
                source_atom_id=atom_id,
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

        # Template fallback
        tmpl = _TEMPLATES.get(technique, _TEMPLATES["source_transparency"])
        lang_tmpl = tmpl.get(lang, tmpl.get("en", {}))
        return PrebunkCard(
            card_id=card_id,
            language=lang,
            technique=technique,
            headline=lang_tmpl.get("headline", ""),
            explanation=lang_tmpl.get("explanation", ""),
            warning_signs=lang_tmpl.get("warning_signs", []),
            verification_guide=lang_tmpl.get("verification_guide", ""),
            source_atom_id=atom_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _build_context(cib_report: dict, tracker_report: dict) -> str:
        summary = cib_report.get("summary", {})
        narratives = tracker_report.get("narratives", [])
        top = narratives[0] if narratives else {}
        return (
            f"CIB signals: {summary.get('flagged_for_review',0)} accounts flagged, "
            f"{summary.get('suspicious_clusters',0)} clusters, "
            f"{summary.get('cross_account_duplicate_pairs',0)} duplicate pairs. "
            f"Top narrative origin: {top.get('origin',{}).get('account_id','unknown')} — "
            f"'{top.get('origin',{}).get('text','')[:100]}'"
        )
