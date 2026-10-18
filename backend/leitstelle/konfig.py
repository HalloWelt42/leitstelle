"""Einstellungen des Kern-Dienstes. Eine Quelle: Umgebungsvariablen mit der Vorsilbe LEITSTELLE_.

Fachliche Regeln (Budget, Fristen, Schwellen) stehen nicht hier, sondern im Regelwerk in der
Datenbank und sind in der Oberfläche einstellbar. Hier steht nur, was der Dienst zum Starten braucht.
"""

from __future__ import annotations

from ipaddress import ip_address, ip_network
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

WURZEL = Path(__file__).resolve().parents[2]


class Konfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEITSTELLE_", env_file=None)

    daten: Path = Field(default=WURZEL / ".run" / "daten", description="Datenordner: Datenbank und Tresorschlüssel")
    host: str = "0.0.0.0"
    port: int = 8530
    oberflaeche: Path | None = Field(default=WURZEL / "frontend" / "dist", description="gebaute Oberfläche; fehlt der Ordner, liefert der Dienst nur die Schnittstellen")
    erlaubte_netze: list[str] = Field(
        default=["127.0.0.0/8", "::1/128", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fd00::/8", "fe80::/10"],
        description="Netze, aus denen Oberfläche und Verwaltung erreichbar sind (Heimnetz und VPN)")
    dienst_takt_s: float = Field(default=5.0, description="Abstand der Zustandsabfrage je Dienst im eigenen Netz")
    extern_abgleich_s: float = Field(default=900.0, description="Abstand der Zustandsabfrage externer Anbieter, wenn sie gesund sind (jede Abfrage zählt für ihre Grenze)")
    pruefung_ab_s: float = Field(default=5.0, description="erster Abstand nach einem Fehlschlag; er verdoppelt sich mit jedem weiteren")
    pruefung_hoechstens_s: float = Field(default=86400.0, description="größter Abstand zwischen zwei Prüfungen eines ausgefallenen Dienstes (ein Tag)")
    ausfall_ab_fehlschlag: int = Field(default=5, description="ab so vielen Fehlschlägen in Folge heißt der Zustand Ausfall statt nicht erreichbar")
    verbindung_s: float = Field(default=10.0, description="Grenze für den Verbindungsaufbau zu Diensten; Arbeit selbst hat keine Lese-Grenze")
    hinweis_s: float = Field(default=15.0, description="Abstand der Wartehinweise in Strömen der Fassade")

    @property
    def datenbank(self) -> Path:
        return self.daten / "leitstelle.sqlite"

    @property
    def tresor_schluessel(self) -> Path:
        return self.daten / "tresor.schluessel"

    def erlaubt(self, adresse: str | None) -> bool:
        """Liegt die Herkunft in einem erlaubten Netz? Ohne Adresse (Tests im Prozess) gilt sie als lokal."""
        if not adresse:
            return True
        try:
            ip = ip_address(adresse)
        except ValueError:
            return adresse in ("testclient", "localhost")
        return any(ip in ip_network(n, strict=False) for n in self.erlaubte_netze)
