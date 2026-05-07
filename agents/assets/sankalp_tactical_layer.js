/**
 * SANKALP TacticalTrackLayer
 * ===========================
 * A Three.js overlay module for the SANKALP geo_map_3d globe.
 * Renders live entity tracks, classification icons, trail histories,
 * radar sweeps, threat arcs, and interactive track-thumbnail panels.
 *
 * Inspired by Anduril's track-thumbnail UI pattern.
 *
 * Usage:
 *   const layer = new TacticalTrackLayer(scene, camera, renderer, globeRadius);
 *   layer.loadTracks(tracksArray);
 *   // In your render loop:
 *   layer.update(deltaTime);
 *
 * Track schema:
 * {
 *   id: "TRK-001",
 *   label: "IAF-SU30-01",
 *   branch: "IAF" | "ARMY" | "NAVY" | "UNKNOWN",
 *   classification: "FRIENDLY" | "HOSTILE" | "NEUTRAL" | "UNKNOWN",
 *   lat: 28.6,
 *   lon: 77.2,
 *   alt: 8000,          // metres (0 = surface)
 *   heading: 45,        // degrees
 *   speed: 850,         // km/h
 *   readiness: 82.5,
 *   assetType: "Su-30MKI",
 *   unit: "Tigers",
 *   history: [[lat, lon], ...],  // max 20 points
 *   threat: false,               // shows threat arc if true
 *   threatRadiusKm: 200,
 *   active: true
 * }
 */

'use strict';

// ── Classification colour palette ──────────────────────────────────────────────
const CLASSIF_COLOR = {
  FRIENDLY: 0x00e676,   // NATO cyan-ish green
  HOSTILE:  0xff4b4b,   // Red
  NEUTRAL:  0xffeb3b,   // Yellow
  UNKNOWN:  0x9e9e9e,   // Grey
};

const CLASSIF_HEX = {
  FRIENDLY: '#00e676',
  HOSTILE:  '#ff4b4b',
  NEUTRAL:  '#ffeb3b',
  UNKNOWN:  '#9e9e9e',
};

const BRANCH_COLOR = {
  IAF:   0x4FC3F7,
  ARMY:  0x81C784,
  NAVY:  0x4DB6AC,
  UNKNOWN: 0x9e9e9e,
};

// ── Geo helpers ────────────────────────────────────────────────────────────────
function latLonAltToVec3(lat, lon, altMetres, globeRadius) {
  const altR  = globeRadius + (altMetres / 6_371_000) * globeRadius * 100;
  const phi   = (90 - lat) * (Math.PI / 180);
  const theta = (lon + 180) * (Math.PI / 180);
  return new THREE.Vector3(
    -altR * Math.sin(phi) * Math.cos(theta),
     altR * Math.cos(phi),
     altR * Math.sin(phi) * Math.sin(theta)
  );
}

function latLonToVec3(lat, lon, r) {
  return latLonAltToVec3(lat, lon, 0, r);
}

function bearingToVec3(lat, lon, headingDeg, r) {
  const hdg = headingDeg * (Math.PI / 180);
  const lat2 = lat + Math.cos(hdg) * 2;
  const lon2 = lon + Math.sin(hdg) * 2;
  return latLonToVec3(lat2, lon2, r + 0.05);
}

// ── Radar sweep circle ────────────────────────────────────────────────────────
function buildSweepRing(lat, lon, radiusKm, globeRadius, color) {
  const deg   = radiusKm / 111.32;
  const pts   = [];
  const STEPS = 80;
  for (let i = 0; i <= STEPS; i++) {
    const a  = (i / STEPS) * Math.PI * 2;
    const la = lat + Math.cos(a) * deg;
    const lo = lon + Math.sin(a) * deg / Math.cos(lat * Math.PI / 180);
    pts.push(latLonToVec3(la, lo, globeRadius + 0.025));
  }
  const geo = new THREE.BufferGeometry().setFromPoints(pts);
  const mat = new THREE.LineBasicMaterial({
    color,
    transparent: true,
    opacity: 0.4,
  });
  return new THREE.Line(geo, mat);
}

// ── Track thumbnail DOM panel ─────────────────────────────────────────────────
function buildThumbnailPanel(track) {
  const panel = document.createElement('div');
  panel.id    = `thumb-${track.id}`;
  panel.style.cssText = `
    position: absolute;
    display: none;
    width: 220px;
    background: rgba(6, 14, 28, 0.93);
    border: 1px solid ${CLASSIF_HEX[track.classification]};
    border-radius: 8px;
    padding: 10px 12px;
    font-family: 'Courier New', monospace;
    font-size: 11px;
    color: #c8e0f4;
    pointer-events: none;
    z-index: 500;
    box-shadow: 0 4px 20px rgba(0,0,0,0.7);
    backdrop-filter: blur(6px);
  `;

  const classifColor = CLASSIF_HEX[track.classification];
  const branchColor  = ({ IAF: '#4FC3F7', ARMY: '#81C784', NAVY: '#4DB6AC' })[track.branch] || '#9e9e9e';
  const readBar      = Math.round(track.readiness || 0);
  const barColor     = readBar >= 60 ? '#00e676' : readBar >= 40 ? '#ff9800' : '#ff4b4b';

  panel.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:7px;">
      <span style="color:${classifColor};font-weight:700;font-size:12px;letter-spacing:1px;">
        ${track.classification}
      </span>
      <span style="background:${classifColor}22;color:${classifColor};
        border:1px solid ${classifColor}55;border-radius:3px;
        padding:1px 6px;font-size:10px;">${track.id}</span>
    </div>
    <div style="color:#7dd3fc;font-size:13px;font-weight:700;margin-bottom:4px;">
      ${track.label}
    </div>
    <div style="color:#64748b;margin-bottom:6px;">${track.assetType || '—'}</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:3px 8px;font-size:10px;margin-bottom:7px;">
      <span style="color:#64748b;">BRANCH</span>
      <span style="color:${branchColor}">${track.branch}</span>
      <span style="color:#64748b;">UNIT</span>
      <span>${track.unit || '—'}</span>
      <span style="color:#64748b;">ALT</span>
      <span>${(track.alt || 0).toLocaleString()} m</span>
      <span style="color:#64748b;">SPEED</span>
      <span>${(track.speed || 0)} km/h</span>
      <span style="color:#64748b;">HDG</span>
      <span>${(track.heading || 0).toFixed(0)}°</span>
      <span style="color:#64748b;">LAT/LON</span>
      <span>${track.lat.toFixed(2)}° ${track.lon.toFixed(2)}°</span>
    </div>
    <div style="margin-bottom:3px;font-size:10px;color:#64748b;">READINESS</div>
    <div style="background:rgba(255,255,255,0.08);border-radius:4px;height:6px;margin-bottom:6px;">
      <div style="background:${barColor};width:${readBar}%;height:6px;border-radius:4px;
        transition:width 0.5s;"></div>
    </div>
    <div style="font-size:10px;color:#64748b;text-align:right;">${readBar}%</div>
    ${track.threat ? `
    <div style="border-top:1px solid rgba(255,75,75,0.3);margin-top:6px;padding-top:6px;">
      <span style="color:#ff4b4b;font-size:10px;font-weight:700;">⚠ THREAT RADIUS: ${track.threatRadiusKm || 0} km</span>
    </div>` : ''}
  `;

  return panel;
}

// ── Main TacticalTrackLayer class ─────────────────────────────────────────────
class TacticalTrackLayer {
  /**
   * @param {THREE.Scene}    scene
   * @param {THREE.Camera}   camera
   * @param {THREE.WebGLRenderer} renderer
   * @param {number}         globeRadius  — must match your globe's SphereGeometry radius
   * @param {HTMLElement}    [container]  — DOM element for thumbnails (defaults to renderer.domElement.parentElement)
   */
  constructor(scene, camera, renderer, globeRadius, container) {
    this.scene       = scene;
    this.camera      = camera;
    this.renderer    = renderer;
    this.R           = globeRadius;
    this.container   = container || renderer.domElement.parentElement;

    // Internal state
    this._tracks      = new Map();   // id → { data, mesh, trail, sweep, panel, arrow }
    this._radarSweeps = new Map();   // id → { line, angle }
    this._rootGroup   = new THREE.Group();
    this._rootGroup.name = 'TacticalLayer';
    scene.add(this._rootGroup);

    // Raycaster for click/hover
    this._raycaster    = new THREE.Raycaster();
    this._mouse        = new THREE.Vector2();
    this._hoveredId    = null;
    this._selectedId   = null;
    this._clickables   = [];         // array of meshes to test

    // Rotation state mirror (must be synced from your render loop)
    this.rotX = 0;
    this.rotY = 0;

    // Bind canvas events
    this._onMouseMove = this._onMouseMove.bind(this);
    this._onClick     = this._onClick.bind(this);
    renderer.domElement.addEventListener('mousemove', this._onMouseMove);
    renderer.domElement.addEventListener('click',     this._onClick);
  }

  // ── Public: load / replace all tracks ──────────────────────────────────────
  loadTracks(tracksArray) {
    // Remove existing
    this.clearAll();
    tracksArray.forEach(t => this.addTrack(t));
  }

  // ── Public: add a single track ──────────────────────────────────────────────
  addTrack(track) {
    if (this._tracks.has(track.id)) this.removeTrack(track.id);

    const group = new THREE.Group();
    group.name  = track.id;

    // ── 1. Main marker dot ──────────────────────────────────────────────────
    const dotRadius = track.classification === 'HOSTILE' ? 0.038 : 0.030;
    const dotGeo    = new THREE.SphereGeometry(dotRadius, 14, 14);
    const dotColor  = CLASSIF_COLOR[track.classification] || 0x9e9e9e;
    const dotMat    = new THREE.MeshPhongMaterial({
      color:            dotColor,
      emissive:         dotColor,
      emissiveIntensity: 0.5,
      shininess:        60,
    });
    const dot = new THREE.Mesh(dotGeo, dotMat);
    const pos = latLonAltToVec3(track.lat, track.lon, track.alt || 0, this.R);
    dot.position.copy(pos);
    dot.userData = { trackId: track.id };
    group.add(dot);
    this._clickables.push(dot);

    // ── 2. Heading arrow (thin line from dot outward) ──────────────────────
    let headingLine = null;
    if (track.heading !== undefined) {
      const from = pos.clone();
      const to   = bearingToVec3(track.lat, track.lon, track.heading, this.R + (track.alt || 0) / 6371000);
      const hGeo = new THREE.BufferGeometry().setFromPoints([from, to]);
      const hMat = new THREE.LineBasicMaterial({
        color:       dotColor,
        transparent: true,
        opacity:     0.7,
      });
      headingLine = new THREE.Line(hGeo, hMat);
      group.add(headingLine);
    }

    // ── 3. Track trail ──────────────────────────────────────────────────────
    let trailLine = null;
    if (track.history && track.history.length > 1) {
      const trailPts = track.history.map(([la, lo]) =>
        latLonAltToVec3(la, lo, track.alt || 0, this.R)
      );
      const tGeo = new THREE.BufferGeometry().setFromPoints(trailPts);
      const tMat = new THREE.LineBasicMaterial({
        color:       dotColor,
        transparent: true,
        opacity:     0.35,
        linewidth:   1,
      });
      trailLine = new THREE.Line(tGeo, tMat);
      group.add(trailLine);
    }

    // ── 4. Hostile: pulsing threat ring ────────────────────────────────────
    let threatRing    = null;
    let threatRingRef = null;
    if (track.classification === 'HOSTILE' || track.threat) {
      const rKm = track.threatRadiusKm || 150;
      const ring = buildSweepRing(track.lat, track.lon, rKm, this.R, 0xff4b4b);
      ring.userData.pulseBase = 0.4;
      threatRing = ring;
      group.add(ring);
    }

    // ── 5. Radar sweep (FRIENDLY assets) ───────────────────────────────────
    let sweepGroup = null;
    if (track.classification === 'FRIENDLY' && track.alt > 3000) {
      const sgp = new THREE.Group();
      sweepGroup = sgp;
      // thin sector wedge as a LineLoop approximating a pie slice
      const sweepPts = [pos.clone()];
      const sweepKm  = 80;
      const deg      = sweepKm / 111.32;
      const SWSTEPS  = 18;
      for (let i = 0; i <= SWSTEPS; i++) {
        const a  = ((i / SWSTEPS) * 0.5 - 0.25) * Math.PI;
        const la = track.lat + Math.cos(a) * deg;
        const lo = track.lon + Math.sin(a) * deg / Math.cos(track.lat * Math.PI / 180);
        sweepPts.push(latLonAltToVec3(la, lo, track.alt || 0, this.R));
      }
      sweepPts.push(pos.clone());
      const swGeo = new THREE.BufferGeometry().setFromPoints(sweepPts);
      const swMat = new THREE.LineBasicMaterial({
        color: 0x00e676, transparent: true, opacity: 0.22
      });
      sgp.add(new THREE.Line(swGeo, swMat));
      this._radarSweeps.set(track.id, { group: sgp, angle: 0 });
      group.add(sgp);
    }

    // ── 6. Thumbnail panel ─────────────────────────────────────────────────
    const panel = buildThumbnailPanel(track);
    this.container.appendChild(panel);

    // ── Store ──────────────────────────────────────────────────────────────
    this._rootGroup.add(group);
    this._tracks.set(track.id, {
      data:      track,
      group,
      dot,
      heading:   headingLine,
      trail:     trailLine,
      threat:    threatRing,
      sweep:     sweepGroup,
      panel,
    });
  }

  // ── Public: remove one track ────────────────────────────────────────────────
  removeTrack(id) {
    const t = this._tracks.get(id);
    if (!t) return;
    this._rootGroup.remove(t.group);
    t.panel.remove();
    this._clickables = this._clickables.filter(m => m.userData.trackId !== id);
    this._tracks.delete(id);
    this._radarSweeps.delete(id);
  }

  // ── Public: update a track's live data (position, speed, etc.) ─────────────
  updateTrack(id, partial) {
    const t = this._tracks.get(id);
    if (!t) return;
    Object.assign(t.data, partial);
    // Reposition dot
    const pos = latLonAltToVec3(t.data.lat, t.data.lon, t.data.alt || 0, this.R);
    t.dot.position.copy(pos);
    // Rebuild panel content
    const fresh = buildThumbnailPanel(t.data);
    t.panel.innerHTML = fresh.innerHTML;
  }

  // ── Public: sync globe rotation (call every frame before update()) ──────────
  syncRotation(rotX, rotY) {
    this.rotX = rotX;
    this.rotY = rotY;
    this._rootGroup.rotation.x = rotX;
    this._rootGroup.rotation.y = rotY;
  }

  // ── Public: main update loop (call in requestAnimationFrame) ────────────────
  update(elapsedSec) {
    const t = elapsedSec;

    this._tracks.forEach((rec, id) => {
      // Hostile pulse
      if (rec.threat) {
        const p = 0.28 + 0.18 * Math.sin(t * 2.8);
        rec.threat.material.opacity = p;
        const s = 1 + 0.06 * Math.sin(t * 2.8);
        rec.threat.scale.setScalar(s);
      }

      // Dot emissive flicker for hostiles
      if (rec.data.classification === 'HOSTILE') {
        rec.dot.material.emissiveIntensity = 0.4 + 0.4 * Math.abs(Math.sin(t * 3.5));
      }

      // Radar sweep rotation (friendly aircraft)
      const sw = this._radarSweeps.get(id);
      if (sw && rec.sweep) {
        sw.angle += 0.02;
        rec.sweep.rotation.set(0, sw.angle, 0);
      }

      // Project dot to screen → update thumbnail position
      this._updatePanelPosition(rec);
    });
  }

  // ── Public: clear all tracks ────────────────────────────────────────────────
  clearAll() {
    this._tracks.forEach((_, id) => this.removeTrack(id));
    this._clickables = [];
  }

  // ── Public: filter visibility by branch or classification ──────────────────
  filterBy({ branch, classification, activeOnly } = {}) {
    this._tracks.forEach((rec) => {
      let visible = true;
      if (branch         && rec.data.branch         !== branch)         visible = false;
      if (classification && rec.data.classification !== classification) visible = false;
      if (activeOnly     && !rec.data.active)                           visible = false;
      rec.group.visible  = visible;
      rec.panel.style.display = visible ? rec.panel.style.display : 'none';
    });
  }

  // ── Public: show all ────────────────────────────────────────────────────────
  showAll() {
    this._tracks.forEach(rec => { rec.group.visible = true; });
  }

  // ── Public: dispose (remove events + scene objects) ────────────────────────
  dispose() {
    this.renderer.domElement.removeEventListener('mousemove', this._onMouseMove);
    this.renderer.domElement.removeEventListener('click',     this._onClick);
    this.clearAll();
    this.scene.remove(this._rootGroup);
  }

  // ── Private: project 3D → 2D and position thumbnail panel ─────────────────
  _updatePanelPosition(rec) {
    const panel = rec.panel;
    if (panel.style.display === 'none') return;

    // World-space position of the dot (after globe rotation)
    const worldPos = rec.dot.getWorldPosition(new THREE.Vector3());
    const ndc = worldPos.clone().project(this.camera);

    // Check if behind the globe (z > 1 in NDC = behind camera)
    if (ndc.z > 1.0) {
      panel.style.display = 'none';
      return;
    }

    const rect    = this.renderer.domElement.getBoundingClientRect();
    const screenX = ((ndc.x + 1) / 2) * rect.width  + rect.left;
    const screenY = ((-ndc.y + 1) / 2) * rect.height + rect.top;

    // Offset panel so it doesn't overlap the marker
    const offX = 20, offY = -20;
    panel.style.left    = `${screenX + offX}px`;
    panel.style.top     = `${Math.max(0, screenY + offY)}px`;
    panel.style.display = 'block';
  }

  // ── Private: mouse move → hover ────────────────────────────────────────────
  _onMouseMove(e) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this._mouse.x =  ((e.clientX - rect.left) / rect.width)  * 2 - 1;
    this._mouse.y = -((e.clientY - rect.top)  / rect.height) * 2 + 1;

    this._raycaster.setFromCamera(this._mouse, this.camera);
    const hits = this._raycaster.intersectObjects(
      this._clickables.filter(m => m.parent.visible)
    );

    // Hide all panels first unless selected
    this._tracks.forEach((rec, id) => {
      if (id !== this._selectedId) rec.panel.style.display = 'none';
    });

    if (hits.length) {
      const id  = hits[0].object.userData.trackId;
      const rec = this._tracks.get(id);
      if (rec) {
        this._hoveredId = id;
        rec.panel.style.display = 'block';
        this._updatePanelPosition(rec);
        this.renderer.domElement.style.cursor = 'crosshair';
      }
    } else {
      this._hoveredId = null;
      this.renderer.domElement.style.cursor = '';
    }
  }

  // ── Private: click → select / deselect ────────────────────────────────────
  _onClick(e) {
    this._raycaster.setFromCamera(this._mouse, this.camera);
    const hits = this._raycaster.intersectObjects(
      this._clickables.filter(m => m.parent.visible)
    );

    if (hits.length) {
      const id = hits[0].object.userData.trackId;
      if (this._selectedId === id) {
        this._selectedId = null;            // deselect
      } else {
        this._selectedId = id;
        // Fire a custom DOM event so Streamlit / Python can listen
        const ev = new CustomEvent('sankalp:trackSelected', {
          detail: this._tracks.get(id)?.data,
          bubbles: true,
        });
        this.renderer.domElement.dispatchEvent(ev);
      }
    } else {
      this._selectedId = null;
    }
  }
}

// ── Static helper: generate sample tracks for India/surrounding region ─────────
TacticalTrackLayer.sampleTracks = function() {
  return [
    // Friendly IAF
    {
      id: 'TRK-001', label: 'IAF-SU30-Alpha', branch: 'IAF',
      classification: 'FRIENDLY', lat: 31.63, lon: 74.87, alt: 9000,
      heading: 35, speed: 920, readiness: 88,
      assetType: 'Su-30MKI', unit: 'Tigers', active: true,
      history: [[31.2,74.3],[31.35,74.5],[31.5,74.68],[31.63,74.87]],
      threat: false,
    },
    {
      id: 'TRK-002', label: 'IAF-TEJAS-01', branch: 'IAF',
      classification: 'FRIENDLY', lat: 26.8, lon: 75.8, alt: 6500,
      heading: 280, speed: 780, readiness: 72,
      assetType: 'Tejas Mk1A', unit: 'Eight Pursoots', active: true,
      history: [[26.6,76.2],[26.65,76.0],[26.72,75.9],[26.8,75.8]],
      threat: false,
    },
    // Friendly Navy
    {
      id: 'TRK-003', label: 'IN-VIKRANT', branch: 'NAVY',
      classification: 'FRIENDLY', lat: 18.93, lon: 72.84, alt: 0,
      heading: 220, speed: 28, readiness: 91,
      assetType: 'INS Vikrant (Carrier)', unit: 'Western Fleet', active: true,
      history: [[19.1,72.9],[19.0,72.88],[18.95,72.85],[18.93,72.84]],
      threat: false,
    },
    // Hostile actors (cross-border simulation)
    {
      id: 'TRK-H01', label: 'HOSTILE-AIR-01', branch: 'UNKNOWN',
      classification: 'HOSTILE', lat: 34.5, lon: 77.2, alt: 11000,
      heading: 190, speed: 1100, readiness: 0,
      assetType: 'Unknown Fast Jet', unit: 'UNKNOWN', active: true,
      history: [[35.2,77.0],[34.9,77.1],[34.7,77.15],[34.5,77.2]],
      threat: true, threatRadiusKm: 250,
    },
    {
      id: 'TRK-H02', label: 'HOSTILE-NAVAL-01', branch: 'UNKNOWN',
      classification: 'HOSTILE', lat: 23.5, lon: 63.8, alt: 0,
      heading: 90, speed: 35, readiness: 0,
      assetType: 'Unknown Destroyer', unit: 'UNKNOWN', active: true,
      history: [[23.4,62.9],[23.42,63.2],[23.46,63.5],[23.5,63.8]],
      threat: true, threatRadiusKm: 180,
    },
    // Neutral
    {
      id: 'TRK-N01', label: 'NEUTRAL-CARGO-01', branch: 'UNKNOWN',
      classification: 'NEUTRAL', lat: 12.0, lon: 75.5, alt: 0,
      heading: 10, speed: 18, readiness: 0,
      assetType: 'Merchant Vessel', unit: 'Civilian', active: true,
      history: [[11.6,75.4],[11.7,75.43],[11.85,75.47],[12.0,75.5]],
      threat: false,
    },
    // Friendly Army
    {
      id: 'TRK-004', label: 'ARMY-T90-01', branch: 'ARMY',
      classification: 'FRIENDLY', lat: 33.5, lon: 77.5, alt: 0,
      heading: 10, speed: 45, readiness: 76,
      assetType: 'T-90 Bhishma', unit: 'Para SF', active: true,
      history: [[33.2,77.3],[33.3,77.38],[33.42,77.44],[33.5,77.5]],
      threat: false,
    },
  ];
};

// ── Export ────────────────────────────────────────────────────────────────────
if (typeof module !== 'undefined' && module.exports) {
  module.exports = TacticalTrackLayer;
} else if (typeof window !== 'undefined') {
  window.TacticalTrackLayer = TacticalTrackLayer;
}
