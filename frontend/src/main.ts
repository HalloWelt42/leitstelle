// Gestaltung aus dem Appkern: Schriften, Marken und die Bausteine des Leitstands; dazu die Symbole und Eigenes
import '@fortawesome/fontawesome-free/css/all.min.css';
import 'appkern-oberflaeche/leitstand.css';
import './stil/app.css';
import { mount } from 'svelte';
import App from './App.svelte';
import { ansichtAnwenden } from './lib/ansicht.svelte';

ansichtAnwenden();
mount(App, { target: document.getElementById('app')! });
