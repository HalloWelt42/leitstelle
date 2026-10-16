// Leitstelle - Untergruppen: eine lange Einstellungsseite in Reiter teilen.
// Liest die Gruppen (section.bereich mit h2) aus dem Rollfeld, baut eine Reiterleiste in den
// festen Kopf und zeigt immer genau eine Gruppe. Pillen zeigen, wo etwas Bedeutsames ansteht.
export function untergruppen({ wurzel, auswahl = ':scope > .bereich', ziel, pillen = {}, aktiv = 0 }) {
  const w = typeof wurzel === 'string' ? document.querySelector(wurzel) : wurzel;
  if (!w) return;
  const gruppen = [...w.querySelectorAll(auswahl)];
  if (gruppen.length < 2) return;
  const leiste = document.createElement('div');
  leiste.className = 'untergruppen';
  const name_von = (g) => {
    const h = g.querySelector('h2'); if (!h) return 'Gruppe';
    const text = [...h.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent.trim()).filter(Boolean).join(' ');
    return text || h.textContent.trim();
  };
  const zeige = (i) => {
    gruppen.forEach((g, k) => g.classList.toggle('sichtbar', k === i));
    [...leiste.children].forEach((b, k) => b.classList.toggle('aktiv', k === i));
  };
  gruppen.forEach((g, i) => {
    const name = name_von(g);
    const symbol = g.querySelector('h2 i')?.className || 'fa-solid fa-circle';
    g.dataset.untergruppe = name;
    const p = pillen[name];
    const b = document.createElement('button');
    b.type = 'button';
    b.title = `Zeigt nur die Gruppe ${name}`;
    b.innerHTML = `<i class="${symbol}"></i>${name}${p ? `<span class="zaehler pille ${p[1] || ''}" title="${p[2] || ''}">${p[0]}</span>` : ''}`;
    if (g.classList.contains('gefahrenzone')) b.classList.add('gefahr');
    b.onclick = () => zeige(i);
    leiste.append(b);
  });
  const kopf = ziel ? document.querySelector(ziel) : document.querySelector('.rahmen-kopf');
  (kopf || w.parentElement).append(leiste);
  zeige(aktiv);
}
