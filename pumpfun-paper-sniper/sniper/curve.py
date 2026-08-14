"""
curve.py -- Bonding-Curve: dekodieren, Preis berechnen, Fills simulieren.

Hintergrund in einem Absatz
---------------------------
Jeder pump.fun-Token hat einen eigenen "Bonding Curve"-Account auf Solana.
Darin stehen zwei Reserven: wie viele Token noch in der Kurve liegen und wie
viel SOL schon drin ist. Der Preis ergibt sich aus dem Verhaeltnis der beiden.
Beim Kauf wandert SOL rein und Token raus, beim Verkauf umgekehrt - nach der
klassischen "Constant Product"-Formel (x * y = k), wie bei Uniswap.

Der Bot liest diesen Account per Solana-RPC aus und rechnet daraus:
  * den aktuellen Preis,
  * wie weit die Kurve schon gelaufen ist (Curve Progress),
  * und - fuer die Simulation - was ein Kauf/Verkauf tatsaechlich einbraechte.

Quellen (Stand August 2026):
  * https://github.com/pump-fun/pump-public-docs  (offizielle Programm-Doku)
  * Programm-ID: 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

#: pump.fun-Hauptprogramm auf Solana Mainnet.
PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

#: Anchor-Discriminator des BondingCurve-Accounts (die ersten 8 Bytes).
#: Damit erkennen wir zuverlaessig, dass wir wirklich eine Bonding Curve vor
#: uns haben und nicht irgendeinen anderen Account.
BONDING_CURVE_DISCRIMINATOR = bytes((0x17, 0xB7, 0xF8, 0x37, 0x60, 0xD8, 0xAC, 0x60))

#: SOL hat 9 Nachkommastellen (1 SOL = 1_000_000_000 Lamports).
LAMPORTS_PER_SOL = 1_000_000_000
#: pump.fun-Token haben 6 Nachkommastellen.
TOKEN_BASE_UNITS = 1_000_000

#: Byte-Offsets im Account (alle u64 little-endian, `complete` ist ein u8/bool).
OFF_VIRTUAL_TOKEN_RESERVES = 0x08
OFF_VIRTUAL_SOL_RESERVES = 0x10
OFF_REAL_TOKEN_RESERVES = 0x18
OFF_REAL_SOL_RESERVES = 0x20
OFF_TOKEN_TOTAL_SUPPLY = 0x28
OFF_COMPLETE = 0x30
#: Neuere Accounts haben hinter `complete` noch die Creator-Pubkey (32 Bytes).
#: Aeltere Accounts sind kuerzer - deshalb wird das Feld optional gelesen.
OFF_CREATOR = 0x31

#: Kleinste sinnvolle Accountgroesse (bis inkl. `complete`).
MIN_ACCOUNT_SIZE = OFF_COMPLETE + 1

#: Virtuelle SOL-Reserve einer frischen pump.fun-Kurve (30 SOL).
#: Daraus folgt eine harte Beziehung, die bei JEDER Standardkurve gilt:
#:     virtual_sol_reserves - 30 SOL == real_sol_reserves
#: Beide Werte bewegen sich bei Kauf und Verkauf um exakt denselben Betrag.
#: Stimmt das nicht, ist es keine Standardkurve - oder wir lesen den Account
#: falsch. In beiden Faellen sind alle abgeleiteten Zahlen wertlos.
INITIAL_VIRTUAL_SOL_RESERVES = 30_000_000_000

#: Standard-Startwert der realen Token-Reserve (fuer den Curve-Progress).
#: Kommt aus dem Global-Account von pump.fun und ist ueber config.yaml
#: (advanced.initial_real_token_reserves) ueberschreibbar.
DEFAULT_INITIAL_REAL_TOKEN_RESERVES = 793_100_000_000_000


class CurveDecodeError(ValueError):
    """Der Account-Inhalt ist keine (gueltige) pump.fun Bonding Curve."""


# ---------------------------------------------------------------------------
# Datenklasse: der Zustand einer Bonding Curve zu einem Zeitpunkt
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CurveState:
    """
    Ein Schnappschuss des Bonding-Curve-Accounts.

    Alle Reserve-Werte sind ROHWERTE in Basiseinheiten (Lamports bzw.
    Token-Mikroeinheiten), so wie sie on-chain stehen. Umgerechnet wird erst in
    den `*_sol` / `*_tokens`-Properties - so gibt es keine Rundungsfehler durch
    mehrfaches Hin- und Herrechnen.
    """

    virtual_token_reserves: int
    virtual_sol_reserves: int
    real_token_reserves: int
    real_sol_reserves: int
    token_total_supply: int
    complete: bool
    creator: bytes | None = None  # 32-Byte-Pubkey, falls im Account vorhanden

    # -- bequeme Umrechnungen --------------------------------------------
    @property
    def virtual_sol(self) -> float:
        """Virtuelle SOL-Reserve in SOL."""
        return self.virtual_sol_reserves / LAMPORTS_PER_SOL

    @property
    def virtual_tokens(self) -> float:
        """Virtuelle Token-Reserve in ganzen Token."""
        return self.virtual_token_reserves / TOKEN_BASE_UNITS

    @property
    def real_sol(self) -> float:
        """Tatsaechlich in der Kurve liegendes SOL."""
        return self.real_sol_reserves / LAMPORTS_PER_SOL

    @property
    def is_tradable(self) -> bool:
        """
        False, sobald der Token migriert ist (dann laeuft der Handel auf
        PumpSwap weiter und die Bonding Curve ist tot).
        """
        return not self.complete and self.virtual_token_reserves > 0 \
            and self.virtual_sol_reserves > 0

    @property
    def layout_deviation_sol(self) -> float:
        """
        Wie weit weicht dieser Account von der Standard-pump.fun-Kurve ab?

        Bei jeder Standardkurve gilt exakt:
            virtual_sol_reserves - 30 SOL == real_sol_reserves
        Beide bewegen sich bei Kauf und Verkauf um denselben Betrag; die
        Gebuehren gehen nicht in die Kurve, sondern an pump.fun.

        Der Rueckgabewert ist die Abweichung in SOL. 0 = perfekt stimmig.
        """
        erwartet = self.virtual_sol_reserves - INITIAL_VIRTUAL_SOL_RESERVES
        return (erwartet - self.real_sol_reserves) / LAMPORTS_PER_SOL

    def is_standard_layout(self, toleranz_sol: float = 1.0) -> bool:
        """
        True, wenn der Account sich wie eine normale pump.fun-Kurve verhaelt.

        Warum das geprueft werden muss: Im Betrieb tauchten Token auf, bei
        denen "Progress 2.2 %" und "Kaufdruck 24.85 SOL" gleichzeitig gemeldet
        wurden. Das schliesst sich aus - bei 2.2 % Progress passen rechnerisch
        nur ~0.5 SOL in die Kurve, 24.85 SOL entspraechen 61 % Progress.

        Solche Accounts sind entweder Kurven mit anderen Parametern oder ein
        anderes Speicherlayout. In beiden Faellen sind ALLE Werte, die dieses
        Programm daraus ableitet, wertlos - Preis, Progress und Kaufdruck
        gleichermassen. Solche Token werden nicht gehandelt.
        """
        return abs(self.layout_deviation_sol) <= toleranz_sol

    @property
    def price_sol(self) -> float:
        """
        Preis pro Token in SOL.

            price = (virtualSolReserves / 1e9) / (virtualTokenReserves / 1e6)

        Bei einer toten/migrierten Kurve gibt es keinen sinnvollen Preis -> 0.0.
        """
        if self.virtual_token_reserves <= 0:
            return 0.0
        return (self.virtual_sol_reserves / LAMPORTS_PER_SOL) / (
            self.virtual_token_reserves / TOKEN_BASE_UNITS
        )

    def progress_pct(
        self,
        initial_real_token_reserves: int = DEFAULT_INITIAL_REAL_TOKEN_RESERVES,
    ) -> float:
        """
        Curve-Progress in Prozent: wie viel der Kurve schon abverkauft ist.

            progress = 1 - (realTokenReserves / INITIAL_REAL_TOKEN_RESERVES)

        0 %   = frisch gelauncht, noch nichts gekauft
        100 % = Kurve voll, Token migriert zu PumpSwap

        Ist der Token bereits `complete`, geben wir 100 % zurueck.
        """
        if self.complete:
            return 100.0
        if initial_real_token_reserves <= 0:
            return 0.0
        ratio = self.real_token_reserves / initial_real_token_reserves
        # Auf 0..100 begrenzen: bei geaenderten Kurvenparametern koennte der
        # Wert sonst leicht negativ oder ueber 100 laufen.
        return max(0.0, min(100.0, (1.0 - ratio) * 100.0))


# ---------------------------------------------------------------------------
# Dekodieren
# ---------------------------------------------------------------------------
def decode_bonding_curve(data: bytes, *, strict_discriminator: bool = True) -> CurveState:
    """
    Zerlegt die Rohbytes eines Bonding-Curve-Accounts in ein `CurveState`.

    `data` sind die base64-dekodierten Bytes aus der RPC-Antwort von
    `getAccountInfo` / `getMultipleAccounts`.

    strict_discriminator=False ist nur fuer Tests gedacht, wenn man einen
    Account ohne korrekten Discriminator bauen will.
    """
    if len(data) < MIN_ACCOUNT_SIZE:
        raise CurveDecodeError(
            f"Account zu klein: {len(data)} Bytes, erwartet mindestens "
            f"{MIN_ACCOUNT_SIZE}."
        )

    if strict_discriminator and data[:8] != BONDING_CURVE_DISCRIMINATOR:
        raise CurveDecodeError(
            "Discriminator passt nicht - das ist keine pump.fun Bonding Curve "
            f"(gefunden: {data[:8].hex()}, erwartet: "
            f"{BONDING_CURVE_DISCRIMINATOR.hex()})."
        )

    # "<Q" = little-endian unsigned 64-bit. struct.unpack_from liest ab Offset.
    (virtual_token_reserves,) = struct.unpack_from("<Q", data, OFF_VIRTUAL_TOKEN_RESERVES)
    (virtual_sol_reserves,) = struct.unpack_from("<Q", data, OFF_VIRTUAL_SOL_RESERVES)
    (real_token_reserves,) = struct.unpack_from("<Q", data, OFF_REAL_TOKEN_RESERVES)
    (real_sol_reserves,) = struct.unpack_from("<Q", data, OFF_REAL_SOL_RESERVES)
    (token_total_supply,) = struct.unpack_from("<Q", data, OFF_TOKEN_TOTAL_SUPPLY)
    complete = data[OFF_COMPLETE] != 0

    # Creator-Pubkey nur lesen, wenn der Account gross genug ist. pump.fun hat
    # das Feld spaeter angehaengt; aeltere Accounts haben es nicht.
    creator: bytes | None = None
    if len(data) >= OFF_CREATOR + 32:
        creator = bytes(data[OFF_CREATOR:OFF_CREATOR + 32])

    return CurveState(
        virtual_token_reserves=virtual_token_reserves,
        virtual_sol_reserves=virtual_sol_reserves,
        real_token_reserves=real_token_reserves,
        real_sol_reserves=real_sol_reserves,
        token_total_supply=token_total_supply,
        complete=complete,
        creator=creator,
    )


# ---------------------------------------------------------------------------
# Fill-Simulation (Constant Product inkl. Gebuehr und Slippage)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BuyQuote:
    """Ergebnis einer simulierten Kauf-Ausfuehrung."""

    sol_in: float             # eingesetztes SOL (brutto, inkl. Gebuehr)
    sol_after_fee: float      # was davon tatsaechlich in die Kurve geht
    fee_sol: float            # abgezogene pump.fun-Gebuehr
    tokens_out: float         # erhaltene Token (nach Slippage)
    avg_price_sol: float      # effektiver Einstiegspreis = sol_in / tokens_out
    spot_price_before: float  # Kurs vor dem Kauf (zum Vergleich)


@dataclass(frozen=True)
class SellQuote:
    """Ergebnis einer simulierten Verkaufs-Ausfuehrung."""

    tokens_in: float          # verkaufte Token
    sol_gross: float          # SOL laut Kurve, vor Gebuehr/Slippage
    fee_sol: float            # abgezogene pump.fun-Gebuehr
    sol_out: float            # tatsaechlich gutgeschriebenes SOL
    avg_price_sol: float      # effektiver Ausstiegspreis = sol_out / tokens_in
    spot_price_before: float


def simulate_buy(
    state: CurveState,
    sol_in: float,
    *,
    fee_pct: float,
    slippage_pct: float,
) -> BuyQuote:
    """
    Simuliert einen Kauf ueber die Bonding Curve.

    Rechenweg (bewusst in derselben Reihenfolge wie on-chain):
      1. pump.fun zieht die Gebuehr vom eingesetzten SOL ab.
         -> `sol_after_fee` landet in der Kurve.
      2. Constant Product: k = vTok * vSol bleibt konstant.
            neue vSol  = vSol + sol_after_fee
            neue vTok  = k / neue vSol
            tokens_out = vTok - neue vTok
         Aequivalent und numerisch stabiler:
            tokens_out = vTok * sol_after_fee / (vSol + sol_after_fee)
      3. Slippage: als Sniper konkurrierst du mit anderen Bots um denselben
         Block. Realistisch bekommst du etwas WENIGER Token als der reine
         Kurvenpreis hergibt - deshalb ziehen wir `slippage_pct` ab.
      4. Sicherheitsnetz: mehr Token als real in der Kurve liegen kann man
         nicht kaufen (`real_token_reserves`).

    Der `simulated_priority_fee_sol` steckt NICHT hier drin - der wird in der
    paper_engine separat vom Guthaben abgezogen, weil er auch dann anfaellt,
    wenn er nichts mit der Kurvenmathematik zu tun hat.
    """
    if sol_in <= 0:
        raise ValueError("sol_in muss groesser als 0 sein.")
    if not state.is_tradable:
        raise ValueError("Diese Bonding Curve ist nicht mehr handelbar (migriert).")

    spot_before = state.price_sol

    # 1) Gebuehr
    fee_sol = sol_in * (fee_pct / 100.0)
    sol_after_fee = sol_in - fee_sol

    # 2) Constant Product - in Basiseinheiten rechnen (ganze Zahlen, exakt)
    lamports_in = sol_after_fee * LAMPORTS_PER_SOL
    v_tok = float(state.virtual_token_reserves)
    v_sol = float(state.virtual_sol_reserves)
    tokens_out_raw = v_tok * lamports_in / (v_sol + lamports_in)

    # 3) Slippage
    tokens_out_raw *= 1.0 - (slippage_pct / 100.0)

    # 4) Deckel: es koennen nie mehr Token rausgehen als real vorhanden sind
    tokens_out_raw = min(tokens_out_raw, float(state.real_token_reserves))
    tokens_out = tokens_out_raw / TOKEN_BASE_UNITS

    if tokens_out <= 0:
        raise ValueError("Simulierter Kauf ergibt 0 Token - Kurve ist leer.")

    return BuyQuote(
        sol_in=sol_in,
        sol_after_fee=sol_after_fee,
        fee_sol=fee_sol,
        tokens_out=tokens_out,
        avg_price_sol=sol_in / tokens_out,
        spot_price_before=spot_before,
    )


def simulate_sell(
    state: CurveState,
    tokens_in: float,
    *,
    fee_pct: float,
    slippage_pct: float,
) -> SellQuote:
    """
    Simuliert einen Verkauf ueber die Bonding Curve.

    Rechenweg:
      1. Constant Product in die andere Richtung:
            sol_gross = vSol * tokens_in / (vTok + tokens_in)
      2. Slippage abziehen (man bekommt real etwas weniger).
      3. pump.fun-Gebuehr abziehen.
      4. Sicherheitsnetz: es kann nie mehr SOL rausfliessen, als real in der
         Kurve liegt (`real_sol_reserves`).
    """
    if tokens_in <= 0:
        raise ValueError("tokens_in muss groesser als 0 sein.")
    if state.virtual_token_reserves <= 0 or state.virtual_sol_reserves <= 0:
        # Tote Kurve: der Verkauf bringt nichts ein (Totalverlust).
        return SellQuote(
            tokens_in=tokens_in,
            sol_gross=0.0,
            fee_sol=0.0,
            sol_out=0.0,
            avg_price_sol=0.0,
            spot_price_before=0.0,
        )

    spot_before = state.price_sol

    # 1) Constant Product
    tokens_in_raw = tokens_in * TOKEN_BASE_UNITS
    v_tok = float(state.virtual_token_reserves)
    v_sol = float(state.virtual_sol_reserves)
    lamports_out = v_sol * tokens_in_raw / (v_tok + tokens_in_raw)

    # 4) Deckel bereits hier: real verfuegbares SOL begrenzt die Auszahlung
    lamports_out = min(lamports_out, float(state.real_sol_reserves))
    sol_gross = lamports_out / LAMPORTS_PER_SOL

    # 2) Slippage
    sol_after_slippage = sol_gross * (1.0 - slippage_pct / 100.0)

    # 3) Gebuehr
    fee_sol = sol_after_slippage * (fee_pct / 100.0)
    sol_out = max(0.0, sol_after_slippage - fee_sol)

    return SellQuote(
        tokens_in=tokens_in,
        sol_gross=sol_gross,
        fee_sol=fee_sol,
        sol_out=sol_out,
        avg_price_sol=sol_out / tokens_in if tokens_in else 0.0,
        spot_price_before=spot_before,
    )


# ---------------------------------------------------------------------------
# Bonding-Curve-Adresse aus der Mint-Adresse ableiten (Fallback)
# ---------------------------------------------------------------------------
def derive_bonding_curve_address(mint: str) -> str | None:
    """
    Berechnet die Bonding-Curve-Adresse aus der Mint-Adresse:
    PDA mit den Seeds [b"bonding-curve", mint] unter dem pump.fun-Programm.

    Wird nur als Fallback gebraucht, falls der Feed einmal keinen
    `bondingCurveKey` mitschickt. Braucht die Bibliothek `solders`; ist die
    nicht installiert, gibt die Funktion None zurueck und der Token wird
    einfach uebersprungen (kein Absturz).
    """
    try:
        from solders.pubkey import Pubkey  # type: ignore import-not-found
    except ImportError:
        return None

    try:
        mint_key = Pubkey.from_string(mint)
        program_id = Pubkey.from_string(PUMP_PROGRAM_ID)
        address, _bump = Pubkey.find_program_address(
            [b"bonding-curve", bytes(mint_key)], program_id
        )
        return str(address)
    except Exception:
        # Ungueltige Mint-Adresse o.ae. - lieber None als ein Crash.
        return None
