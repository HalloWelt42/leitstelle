// Telefone bekommen eine eigenständige, reduzierte Ansicht statt einer gequetschten Schreibtischfassung. Der Haltepunkt
// steht nur hier, und die Weiche gilt auch, wenn sich die Fensterbreite später ändert: schmal führt zur Mobilseite,
// breit zurück zur Seite, die vorher offen war.
import { weg, type Seite } from './weg.svelte';

const TELEFON = '(max-width: 700px)';

export function telefonweicheStarten(): void {
  const abfrage = matchMedia(TELEFON);
  let vorher: { seite: Seite; teil: string | null } = { seite: 'uebersicht', teil: null };
  const stellen = (schmal: boolean): void => {
    if (schmal && weg.seite !== 'mobil') {
      vorher = { seite: weg.seite, teil: weg.teil };
      weg.gehe('mobil', null, true);
    } else if (!schmal && weg.seite === 'mobil') {
      weg.gehe(vorher.seite, vorher.teil, true);
    }
  };
  stellen(abfrage.matches);
  abfrage.addEventListener('change', (e) => stellen(e.matches));
}
