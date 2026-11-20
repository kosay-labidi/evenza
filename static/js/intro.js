/* =====================================================================
   Évenza · intro 3D facultative
   Une terrasse méditerranéenne au crépuscule, construite en code (Three.js),
   animée par GSAP. Aucun fichier 3D à télécharger.
   - « Passer l'intro » ou Échap à tout moment
   - si la scène n'est pas prête en 1,5 s, le site s'affiche directement
   - version allégée sur téléphone et appareils modestes
   - la page d'accueil est déjà chargée dessous : rien ne dépend de cette intro
   ===================================================================== */
(() => {
  const ctx = window.__evenzaIntro; if (!ctx) return;
  const { el, charger } = ctx;
  const html = document.documentElement, main = document.getElementById('contenu');
  const btnGo = el.querySelector('[data-intro-go]'), btnSkip = el.querySelector('[data-intro-skip]');
  const btnSound = el.querySelector('[data-intro-sound]'), audioAmbiance = el.querySelector('[data-intro-audio]');
  let fini = false, renderer = null, raf = 0;

  function brancherSon(audio, btn, vol) {
    if (!audio || !btn) return { stop() {} };
    audio.volume = vol; audio.muted = true;
    const ko = () => { btn.hidden = true; try { audio.remove(); } catch (e) {} };
    audio.addEventListener('error', ko, { once: true });
    audio.addEventListener('canplaythrough', () => { btn.hidden = false; }, { once: true });
    audio.load();
    btn.addEventListener('click', () => {
      audio.muted = !audio.muted;
      if (!audio.muted) audio.play().catch(() => {});
      btn.textContent = audio.muted ? 'Son' : 'Muet';
      btn.setAttribute('aria-pressed', String(!audio.muted));
    });
    audio.play().catch(() => {});
    return { stop() { audio.pause(); } };
  }
  const son = brancherSon(audioAmbiance, btnSound, 0.18);

  // ---------- fin de l'intro : retour au site ----------
  function fin(rapide) {
    if (fini) return; fini = true;
    try { sessionStorage.setItem('evenza-intro', 'vue'); } catch (e) {}
    const termine = () => {
      cancelAnimationFrame(raf);
      removeEventListener('resize', taille); removeEventListener('keydown', clavier);
      if (renderer) { renderer.dispose(); if (renderer.forceContextLoss) renderer.forceContextLoss(); }
      son.stop();
      el.remove(); html.classList.remove('intro-on'); html.classList.add('intro-revele');
      if (main) main.inert = false;
      const t = document.getElementById('mx-titre');
      if (t) { t.setAttribute('tabindex', '-1'); t.focus({ preventScroll: true }); }
    };
    const d = rapide ? 450 : 700;
    el.style.transition = `opacity ${d}ms ease`; el.style.opacity = '0'; el.classList.add('fin');
    html.classList.add('intro-revele');
    setTimeout(termine, d + 10);
  }
  window.__evenzaIntroFin = () => fin(true);
  btnSkip.addEventListener('click', () => fin(true));
  function clavier(e) {
    if (e.key === 'Escape') fin(true);
    if (e.key === 'Tab') { // la focalisation reste dans l'intro
      const b = [btnGo, btnSkip].filter(x => x.style.visibility !== 'hidden' && getComputedStyle(x).visibility !== 'hidden');
      if (!b.length) return;
      const i = b.indexOf(document.activeElement);
      e.preventDefault(); b[(i + (e.shiftKey ? -1 : 1) + b.length) % b.length].focus();
    }
  }
  addEventListener('keydown', clavier);
  btnSkip.focus({ preventScroll: true });

  let taille = () => {};
  Promise.all([charger(el.dataset.three), charger(el.dataset.gsap)])
    .then(() => { if (!fini) demarrer(); })
    .catch(() => fin(true));

  // ---------- la scène ----------
  function demarrer() {
    const T = window.THREE, gsap = window.gsap;
    const mobile = matchMedia('(max-width: 760px)').matches || (matchMedia('(pointer: coarse)').matches && !matchMedia('(any-pointer: fine)').matches);
    const faible = mobile || (navigator.hardwareConcurrency || 8) <= 4 || !!(navigator.connection && navigator.connection.saveData);
    const canvas = el.querySelector('canvas');
    try {
      renderer = new T.WebGLRenderer({ canvas, antialias: !faible, powerPreference: 'high-performance' });
    } catch (e) { fin(true); return; }
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, faible ? 1.25 : 1.75));
    renderer.outputEncoding = T.sRGBEncoding;
    renderer.toneMapping = T.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    canvas.addEventListener('webglcontextlost', () => fin(true));

    const scene = new T.Scene();
    scene.fog = new T.Fog(0xE2AE86, 50, 420);
    const cam = new T.PerspectiveCamera(48, 1, 0.1, 1400);
    taille = () => {
      const w = innerWidth, h = innerHeight;
      renderer.setSize(w, h, false); cam.aspect = w / h; cam.fov = w / h < 0.8 ? 64 : 48; cam.updateProjectionMatrix();
    };
    taille(); addEventListener('resize', taille);

    const soleil = new T.Vector3(0.04, 0.055, 1).normalize();
    const soleil0 = soleil.clone();
    const std = (c, o = {}) => new T.MeshStandardMaterial(Object.assign({ color: c, roughness: 0.9, metalness: 0 }, o));
    const ajoute = (g, m, x, y, z) => { const o = new T.Mesh(g, m); o.position.set(x, y, z); scene.add(o); return o; };

    // ciel du soir (dégradé + soleil)
    const ciel = new T.Mesh(new T.SphereGeometry(900, 32, 16), new T.ShaderMaterial({
      side: T.BackSide, depthWrite: false, fog: false, uniforms: { sun: { value: soleil } },
      vertexShader: 'varying vec3 vD; void main(){ vD = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
      fragmentShader: `varying vec3 vD; uniform vec3 sun;
        void main(){
          float h = vD.y;
          vec3 top = vec3(.11,.19,.34), mid = vec3(.79,.49,.42), low = vec3(.98,.80,.60);
          vec3 c = mix(low, mid, smoothstep(.0, .16, h)); c = mix(c, top, smoothstep(.14, .62, h));
          float d = max(dot(normalize(vD), sun), 0.0);
          c += vec3(1., .74, .45) * pow(d, 30.) * .55 + vec3(1., .93, .78) * smoothstep(.9993, .9997, d) * 1.4;
          if (h < 0.) c = mix(low, vec3(.84,.62,.50), smoothstep(0., -.08, h));
          gl_FragColor = vec4(c, 1.);
        }`
    }));
    scene.add(ciel);

    // mer animée (reflets du soleil)
    const mer = new T.Mesh(new T.PlaneGeometry(2400, 1400, 1, 1), new T.ShaderMaterial({
      fog: false, uniforms: { t: { value: 0 }, sun: { value: soleil } },
      vertexShader: 'varying vec3 vW; void main(){ vec4 w = modelMatrix * vec4(position, 1.0); vW = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }',
      fragmentShader: `varying vec3 vW; uniform float t; uniform vec3 sun;
        void main(){
          vec2 p = vW.xz;
          vec3 n = normalize(vec3(
            cos(p.x*.35 + t*.9)*.07 + cos(p.x*1.7 - p.y*1.3 + t*2.1)*.05 + cos(p.x*4.1 + t*3.)*.025,
            1.,
            cos(p.y*.22 - t*.7)*.07 + cos((p.x + p.y)*.6 + t*1.3)*.05 + cos(p.y*3.7 - t*2.6)*.025));
          vec3 v = normalize(vW - cameraPosition);
          vec3 r = reflect(v, n);
          float spec = pow(max(dot(r, sun), 0.), 88.);
          float spec2 = pow(max(dot(r, sun), 0.), 16.);
          float fres = pow(1. - max(dot(-v, n), 0.), 3.4);
          vec3 c = mix(vec3(.06,.18,.30), vec3(.96,.70,.54), fres * .95)
                 + vec3(1., .86, .58) * spec * 3.6
                 + vec3(1., .90, .72) * spec2 * .7;
          float d = length(vW.xz - cameraPosition.xz);
          c = mix(c, vec3(.97,.80,.62), smoothstep(90., 420., d));
          c = mix(c, vec3(.94,.84,.72), smoothstep(180., 500., d) * .5);
          gl_FragColor = vec4(c, 1.);
        }`
    }));
    mer.rotation.x = -Math.PI / 2; mer.position.set(0, -6, 650); scene.add(mer);
    const brume = new T.Mesh(new T.PlaneGeometry(2600, 90), new T.MeshBasicMaterial({
      color: 0xF4D3A2, transparent: true, opacity: 0.22, depthWrite: false, fog: false
    }));
    brume.position.set(0, 10, 360); scene.add(brume);

    // caps lointains
    const cap = std(0x8A6A72, { flatShading: true });
    [[-230, 360, 70, 22], [150, 420, 90, 18], [330, 330, 60, 14]].forEach(([x, z, r, h]) => {
      const c = ajoute(new T.ConeGeometry(r, h, 7), cap, x, -6 + h / 2 - 2, z); c.scale.z = 0.45;
    });

    // lumières
    scene.add(new T.HemisphereLight(0xFFE2C4, 0x5E4C48, 0.8));
    const dl = new T.DirectionalLight(0xFFB27A, 1.55); dl.position.copy(soleil).multiplyScalar(100).add(new T.Vector3(-30, 30, 0)); scene.add(dl);

    // terrasse, falaise, balustrade
    const pierre = std(0xE7D7BD), blanc = std(0xF7F2EA, { roughness: 0.95 }), bleu = std(0x2B5CA6, { roughness: 0.45 });
    ajoute(new T.BoxGeometry(80, 1, 40), pierre, 0, -0.5, -20);
    ajoute(new T.BoxGeometry(80, 8, 2), std(0xC9B08F), 0, -4.5, -0.6);
    ajoute(new T.BoxGeometry(80, 0.16, 0.34), blanc, 0, 1.05, -0.3);
    const nbP = faible ? 70 : 130, poteaux = new T.InstancedMesh(new T.BoxGeometry(0.13, 1, 0.13), blanc, nbP);
    const m4 = new T.Matrix4();
    for (let i = 0; i < nbP; i++) { m4.makeTranslation(-39 + i * (78 / (nbP - 1)), 0.5, -0.3); poteaux.setMatrixAt(i, m4); }
    scene.add(poteaux);

    // façade blanche à arches + intérieur chaud
    const largeur = 34, haut = 7.5, forme = new T.Shape();
    forme.moveTo(0, 0); forme.lineTo(largeur, 0); forme.lineTo(largeur, haut); forme.lineTo(0, haut); forme.lineTo(0, 0);
    for (let cx = 3; cx < largeur - 1; cx += 4) {
      const t = new T.Path(); t.moveTo(cx - 1.05, 0.35); t.lineTo(cx - 1.05, 3.5);
      t.absarc(cx, 3.5, 1.05, Math.PI, 0, true); t.lineTo(cx + 1.05, 0.35); t.lineTo(cx - 1.05, 0.35);
      forme.holes.push(t);
    }
    ajoute(new T.ExtrudeGeometry(forme, { depth: 0.9, bevelEnabled: false }), blanc, -26, 0, -22.9);
    const interieur = std(0x3A2A22, { emissive: 0xFFA860, emissiveIntensity: 0 });
    ajoute(new T.BoxGeometry(34, 7, 3.6), interieur, -9, 3.5, -25);
    ajoute(new T.BoxGeometry(24, 3.6, 6), blanc, -12, 9.3, -25.5);
    for (let x = -21; x <= -3; x += 4.5) ajoute(new T.BoxGeometry(1.2, 1.7, 0.18), bleu, x, 9.3, -22.45);
    const coupole = ajoute(new T.SphereGeometry(2.9, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2), bleu, -12, 11.7, -25.5);
    ajoute(new T.CylinderGeometry(3, 3, 0.6, 32), blanc, -12, 11.4, -25.5); coupole.scale.y = 0.9;
    ajoute(new T.BoxGeometry(5, 12.5, 5), blanc, 11, 6.25, -26);
    ajoute(new T.BoxGeometry(1.7, 2.9, 0.2), bleu, 11, 1.45, -23.45);
    ajoute(new T.BoxGeometry(1.2, 1.6, 0.2), bleu, 11, 8.6, -23.45);

    // bougainvillier et pots bleus
    const ico = new T.IcosahedronGeometry(0.36, 0);
    const nbB = faible ? 40 : 90, bougain = new T.InstancedMesh(ico, std(0xC23F7C, { roughness: 0.8 }), nbB);
    for (let i = 0; i < nbB; i++) {
      const a = Math.random();
      m4.makeTranslation(-26 + a * 9 + Math.random() * 0.6, 6.4 + Math.sin(a * 3) * 1.2 + Math.random() * 1.2, -22 + Math.random() * 0.7);
      bougain.setMatrixAt(i, m4);
    }
    scene.add(bougain);
    const pot = std(0x2B5CA6, { roughness: 0.35 }), feuille = std(0x5F7F4E);
    [-24, -16, -4, 4, 17].forEach(x => { ajoute(new T.CylinderGeometry(0.5, 0.36, 0.9, 16), pot, x, 0.45, -20.6); ajoute(new T.IcosahedronGeometry(0.75, 1), feuille, x, 1.45, -20.6); });

    // guirlandes lumineuses
    const lueur = (() => {
      const c = document.createElement('canvas'); c.width = c.height = 64;
      const g = c.getContext('2d'), r = g.createRadialGradient(32, 32, 0, 32, 32, 32);
      r.addColorStop(0, 'rgba(255,240,200,1)'); r.addColorStop(0.25, 'rgba(255,200,120,.85)'); r.addColorStop(1, 'rgba(255,180,90,0)');
      g.fillStyle = r; g.fillRect(0, 0, 64, 64); return new T.CanvasTexture(c);
    })();
    const ampoules = [], fil = new T.LineBasicMaterial({ color: 0x3B2E26 });
    const xs = faible ? [-16, -4, 8] : [-20, -12, -4, 4, 12];
    xs.forEach(x => {
      ajoute(new T.CylinderGeometry(0.06, 0.06, 4.6, 6), std(0x3B2E26), x + 1.5, 2.3, -1.4);
      const a = new T.Vector3(x, 7.4, -22), b = new T.Vector3(x + 1.5, 4.5, -1.4), pts = [];
      for (let i = 0; i <= 20; i++) { const k = i / 20, p = a.clone().lerp(b, k); p.y -= Math.sin(k * Math.PI) * 1.3; pts.push(p); if (i % 1 === 0 && i > 0 && i < 20) ampoules.push(p.x, p.y - 0.12, p.z); }
      scene.add(new T.Line(new T.BufferGeometry().setFromPoints(pts), fil));
    });
    const geoA = new T.BufferGeometry(); geoA.setAttribute('position', new T.Float32BufferAttribute(ampoules, 3));
    const matA = new T.PointsMaterial({ size: 0.9, map: lueur, color: 0xFFD28A, transparent: true, opacity: 0, depthWrite: false, blending: T.AdditiveBlending });
    scene.add(new T.Points(geoA, matA));
    const chaudes = [];
    (faible ? [-4] : [-14, -2, 10]).forEach(x => { const l = new T.PointLight(0xFFB870, 0, 16, 2); l.position.set(x, 5, -10); scene.add(l); chaudes.push(l); });

    // tables dressées avec bougies
    const nappe = std(0xFBF7F0, { roughness: 1 }), bougies = [];
    [[-18, -12], [-8, -16], [7, -16], [15, -9], [-15, -5]].slice(0, faible ? 3 : 5).forEach(([x, z]) => {
      ajoute(new T.CylinderGeometry(0.95, 1.02, 0.8, 24), nappe, x, 0.4, z);
      ajoute(new T.CylinderGeometry(0.06, 0.06, 0.22, 8), blanc, x - 0.25, 0.92, z); ajoute(new T.CylinderGeometry(0.06, 0.06, 0.22, 8), blanc, x + 0.25, 0.92, z);
      ajoute(new T.IcosahedronGeometry(0.2, 0), std(0xF2BDB4), x, 0.95, z + 0.25);
      bougies.push(x - 0.25, 1.1, z, x + 0.25, 1.1, z);
    });

    // arche fleurie face à la mer
    const AX = 2, AZ = -3, R = 2;
    ajoute(new T.CylinderGeometry(0.09, 0.09, 2.5, 8), blanc, AX - R, 1.25, AZ);
    ajoute(new T.CylinderGeometry(0.09, 0.09, 2.5, 8), blanc, AX + R, 1.25, AZ);
    ajoute(new T.TorusGeometry(R, 0.09, 8, 48, Math.PI), blanc, AX, 2.5, AZ);
    const nbF = faible ? 160 : 420, fleurs = new T.InstancedMesh(new T.IcosahedronGeometry(0.1, 1), std(0xFFFFFF, { roughness: 0.7 }), nbF);
    const teintes = [0xF2C2BA, 0xFFFFFF, 0xF7E2D6, 0xE7A39A, 0x6F8F5E].map(c => new T.Color(c)), q = new T.Vector3();
    for (let i = 0; i < nbF; i++) {
      const k = Math.random();
      if (k < 0.62) { const a = Math.random() * Math.PI; q.set(AX + Math.cos(a) * R, 2.5 + Math.sin(a) * R, AZ); }
      else { const s = Math.random() < 0.5 ? -1 : 1; q.set(AX + s * R, Math.random() * 2.5, AZ); }
      q.x += (Math.random() - 0.5) * 0.45; q.y += (Math.random() - 0.5) * 0.45; q.z += (Math.random() - 0.5) * 0.45;
      const sc = 0.6 + Math.random() * 1.0; m4.makeScale(sc, sc, sc).setPosition(q); fleurs.setMatrixAt(i, m4);
      fleurs.setColorAt(i, teintes[Math.random() < 0.2 ? 4 : Math.floor(Math.random() * 4)]);
    }
    scene.add(fleurs);

    // allée vers l'arche : tapis ivoire, pétales et lanternes
    ajoute(new T.BoxGeometry(1.7, 0.03, 9.5), std(0xF8F1E6, { roughness: 1 }), AX, 0.015, AZ - 5.2);
    const nbPe = faible ? 60 : 140, petales = new T.InstancedMesh(new T.CircleGeometry(0.07, 6), std(0xEFA9A0, { side: T.DoubleSide }), nbPe);
    for (let i = 0; i < nbPe; i++) {
      m4.makeRotationX(-Math.PI / 2).setPosition(AX + (Math.random() - 0.5) * 1.6, 0.04, AZ - 0.5 - Math.random() * 9.5); petales.setMatrixAt(i, m4);
    }
    scene.add(petales);
    const lanterne = std(0xF2E9DA, { roughness: 0.6 });
    for (let z = AZ - 1.6; z > AZ - 10; z -= 1.7) [-1.25, 1.25].forEach(dx => {
      ajoute(new T.CylinderGeometry(0.13, 0.15, 0.36, 6), lanterne, AX + dx, 0.18, z);
      bougies.push(AX + dx, 0.24, z);
    });

    const geoB = new T.BufferGeometry(); geoB.setAttribute('position', new T.Float32BufferAttribute(bougies, 3));
    const matB = new T.PointsMaterial({ size: 0.55, map: lueur, color: 0xFFC27A, transparent: true, opacity: 0, depthWrite: false, blending: T.AdditiveBlending });
    scene.add(new T.Points(geoB, matB));

    // ---------- trajectoire de la caméra ----------
    const V = (x, y, z) => new T.Vector3(x, y, z);
    const chemin = new T.CatmullRomCurve3([V(0, 8.5, 36), V(-5, 5.5, 18), V(-15, 3.2, 5), V(-14, 2.7, -8), V(-5, 2.3, -12), V(AX, 1.95, -12.5)], false, 'centripetal');
    const vise = new T.CatmullRomCurve3([V(0, 3, -12), V(-6, 3, -16), V(-12, 3.6, -22), V(-6, 3.4, -22), V(6, 2.6, -12), V(AX, 2.45, 8)], false, 'centripetal');
    const etat = { p: mobile ? 0.6 : 0, q: 0, lum: 0, calme: 0 };
    const pos = new T.Vector3(), cible = new T.Vector3(), base = new T.Vector3(), baseC = new T.Vector3();
    const arche = V(AX, 1.88, AZ + 0.2), sortie = V(AX, 2.32, 24), sortieC = V(AX, 2.85, 95);
    const viseArche = V(AX, 2.35, 18);
    const vignette = el.querySelector('.intro-arch-vignette');

    function placer(t) {
      chemin.getPointAt(Math.min(etat.p, 1), pos); vise.getPointAt(Math.min(etat.p, 1), cible);
      const a = 0.14 * etat.calme;
      pos.x += Math.sin(t * 0.35) * a; pos.y += Math.sin(t * 0.5) * a * 0.5; cible.x += Math.sin(t * 0.27) * a * 0.6;
      if (etat.q > 0) {
        if (etat.q < 0.42) {
          const k = etat.q / 0.42;
          pos.copy(base).lerp(arche, k); cible.copy(baseC).lerp(viseArche, k);
        } else {
          const k = (etat.q - 0.42) / 0.58;
          pos.copy(arche).lerp(sortie, k); cible.copy(viseArche).lerp(sortieC, k);
        }
        if (vignette) vignette.style.opacity = String(Math.min(1, etat.q * 1.35));
      }
      cam.position.copy(pos); cam.lookAt(cible);
    }
    function lumieres() {
      matA.opacity = etat.lum; matB.opacity = etat.lum * 0.9;
      interieur.emissiveIntensity = etat.lum * 0.4;
      chaudes.forEach(l => { l.intensity = etat.lum * 1.4; });
    }

    // ---------- animation ----------
    const brand = el.querySelector('.intro-brand'), line = el.querySelector('.intro-line');
    const duree = mobile ? 2.6 : 7.2;
    const tl = gsap.timeline({ onUpdate: lumieres });
    tl.to(etat, { p: 1, duration: duree, ease: 'power2.inOut' }, 0)
      .to(etat, { lum: 1, duration: mobile ? 1.4 : 2.8, ease: 'sine.inOut' }, mobile ? 0.3 : 2.2)
      .to(brand, { opacity: 1, y: 0, duration: 1.2, ease: 'power3.out' }, mobile ? 0.2 : 0.8)
      .to(line, { opacity: 1, duration: 1, ease: 'sine.out' }, mobile ? 0.6 : 1.6)
      .to(btnGo, { autoAlpha: 1, duration: 0.8, ease: 'power2.out', onComplete: () => btnGo.focus({ preventScroll: true }) }, duree - (mobile ? 0.4 : 0.9))
      .to(etat, { calme: 1, duration: 2, ease: 'sine.inOut' }, duree - 0.4);

    btnGo.addEventListener('click', () => {
      if (fini) return;
      tl.pause(); base.copy(cam.position); baseC.copy(cible);
      const veil = el.querySelector('.intro-veil');
      if (veil) { veil.style.opacity = 0; veil.style.clipPath = 'circle(0% at 50% 52%)'; }
      const dur = mobile ? 1.6 : 2.2;
      gsap.timeline({ onComplete: () => fin(false) })
        .to([btnGo, line, brand, btnSkip, btnSound].filter(Boolean), { autoAlpha: 0, duration: 0.35 }, 0)
        .to(etat, { q: 0.42, duration: dur * 0.42, ease: 'power3.in' }, 0)
        .to(etat, { q: 1, duration: dur * 0.58, ease: 'expo.in' }, dur * 0.42)
        .to(cam, { fov: cam.fov * 0.55, duration: dur, ease: 'power2.in', onUpdate: () => cam.updateProjectionMatrix() }, 0)
        .to('.intro-veil', { opacity: 1, clipPath: 'circle(140% at 50% 52%)', scale: 1, duration: 0.7, ease: 'expo.in' }, dur * 0.75);
    });

    // ---------- boucle de rendu ----------
    const horloge = new T.Clock();
    let premier = true;
    (function boucle() {
      raf = requestAnimationFrame(boucle);
      if (document.hidden) return;
      const t = horloge.getElapsedTime();
      mer.material.uniforms.t.value = t;
      const sunT = t * 0.6; // léger balancement du soleil (période ~10 s)
      soleil.copy(soleil0);
      soleil.x += Math.sin(sunT) * 0.09;
      soleil.y += Math.sin(sunT * 0.65) * 0.018;
      soleil.normalize();
      ciel.material.uniforms.sun.value.copy(soleil);
      mer.material.uniforms.sun.value.copy(soleil);
      dl.position.copy(soleil).multiplyScalar(100).add(new T.Vector3(-30, 30, 0));
      placer(t);
      renderer.render(scene, cam);
      if (premier) { premier = false; el.classList.add('pret'); }
    })();
  }
})();
