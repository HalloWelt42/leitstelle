<script lang="ts">
  // Name eines Modells oder Dienstes: das echte Modell vorn, die Aufgabe klein dahinter ("Whisper Large V3 ·
  // Spracherkennung"). Die Aufgabe meldet der Dienst (Maschinenraum); leer, wenn der Name sie schon nennt.
  let { name, aufgabe = '' }: { name: string; aufgabe?: string } = $props();
</script>

{name}{#if aufgabe}<span class="aufgabe"> · {aufgabe}</span>{/if}
