"use client";

import React, { useEffect, useRef, useState, useMemo, useCallback } from "react";
import "leaflet/dist/leaflet.css";

const MAPTILER_KEY = "CRFoY3RXgAloQLarTcRL";

// High-performance tile styles with pre-buffered caching
const TILE_STYLES: Record<string, { name: string; url: string; subdomains?: string[]; maxZoom: number }> = {
  voyager: {
    name: "Cream SCADA (Fast)",
    url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
    subdomains: ["a", "b", "c", "d"],
    maxZoom: 19,
  },
  dataviz: {
    name: "Dark SCADA",
    url: `https://api.maptiler.com/maps/dataviz-dark/256/{z}/{x}/{y}.png?key=${MAPTILER_KEY}`,
    maxZoom: 19,
  },
  hybrid: {
    name: "Satellite Aerial",
    url: `https://api.maptiler.com/maps/hybrid/256/{z}/{x}/{y}.jpg?key=${MAPTILER_KEY}`,
    maxZoom: 19,
  },
  streets: {
    name: "Highways & Grid",
    url: `https://api.maptiler.com/maps/streets-v2-dark/256/{z}/{x}/{y}.png?key=${MAPTILER_KEY}`,
    maxZoom: 19,
  },
};

interface GridMapProps {
  markers: Array<{
    asset_id: string;
    asset_type?: string;
    name?: string;
    latitude: number;
    longitude: number;
    risk_level: string;
    overall_risk_score?: number;
    customers_served?: number;
    voltage_kv?: number;
    capacity_mva?: number;
    district?: string;
  }>;
  selectedAssetId?: string;
  onSelectAsset?: (assetId: string) => void;
}

export default function GridMap({
  markers = [],
  selectedAssetId,
  onSelectAsset,
}: GridMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const canvasRendererRef = useRef<any>(null);
  const markersLayerRef = useRef<any>(null);
  const linesLayerRef = useRef<any>(null);
  const selectedMarkerLayerRef = useRef<any>(null);
  const tileLayerRef = useRef<any>(null);

  const [currentStyle, setCurrentStyle] = useState<string>("voyager");
  const [showPowerLines, setShowPowerLines] = useState<boolean>(true);

  const onSelectRef = useRef(onSelectAsset);
  onSelectRef.current = onSelectAsset;

  const selectedRef = useRef(selectedAssetId);
  selectedRef.current = selectedAssetId;

  // Pre-calculate transmission interconnect line segments between nearest substations
  const transmissionLines = useMemo(() => {
    const substations = markers.filter(
      (a) =>
        (a.asset_type === "substation" ||
          a.asset_type === "power_plant" ||
          a.asset_id.startsWith("SS-") ||
          a.asset_id.startsWith("PP-")) &&
        a.latitude &&
        a.longitude
    );

    if (substations.length < 2) return [];

    const lines: Array<[[number, number], [number, number]]> = [];
    const connectedPairs = new Set<string>();

    for (let i = 0; i < substations.length; i++) {
      const s1 = substations[i];
      const neighbors = substations
        .filter((_, idx) => idx !== i)
        .map((s2) => ({
          s2,
          dist: Math.hypot(s1.latitude - s2.latitude, s1.longitude - s2.longitude),
        }))
        .sort((a, b) => a.dist - b.dist)
        .slice(0, 2);

      neighbors.forEach(({ s2, dist }) => {
        if (dist < 1.8) {
          const pairKey = [s1.asset_id, s2.asset_id].sort().join("::");
          if (!connectedPairs.has(pairKey)) {
            connectedPairs.add(pairKey);
            lines.push([
              [s1.latitude, s1.longitude],
              [s2.latitude, s2.longitude],
            ]);
          }
        }
      });
    }
    return lines;
  }, [markers]);

  // Construct Starbucks Themed Inspector Popup HTML on demand
  const buildPopupContent = useCallback((asset: any) => {
    const risk = (asset.risk_level || "MEDIUM").toUpperCase();
    const color =
      risk === "CRITICAL"
        ? "#c82014"
        : risk === "HIGH"
        ? "#e67e22"
        : risk === "MEDIUM"
        ? "#cba258"
        : "#00754A";

    const isPowerPlant = asset.asset_type === "power_plant" || asset.asset_id.startsWith("PP-");
    const isSubstation = asset.asset_type === "substation" || asset.asset_id.startsWith("SS-");

    return `
      <div style="background: #ffffff; color: rgba(0,0,0,0.87); border-radius: 12px; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 11px; border: 1px solid #e7e5e0; min-width: 200px; box-shadow: 0 10px 26px rgba(0,0,0,0.18);">
        <div style="background: #1E3932; color: #ffffff; padding: 10px 14px; display: flex; align-items: center; justify-content: space-between;">
          <div>
            <div style="font-weight: 700; font-size: 13px; letter-spacing: -0.01em;">${asset.asset_id}</div>
            <div style="font-size: 9px; color: rgba(255,255,255,0.7); text-transform: uppercase;">
              ${isPowerPlant ? "🏭 Power Generation Station" : isSubstation ? "⚡ GETCO Substation" : "🔌 Distribution Transformer (TR)"}
            </div>
          </div>
          <span style="background: ${color}; color: #ffffff; font-weight: 700; font-size: 9px; padding: 2px 7px; border-radius: 50px; text-transform: uppercase;">
            ${risk}
          </span>
        </div>
        <div style="padding: 10px 14px; background: #faf9f6;">
          <div style="color: rgba(0,0,0,0.7); font-size: 10px; margin-bottom: 6px; font-weight: 600;">
            ${asset.name || "Gujarat Power Grid"} &bull; ${asset.district || "Gujarat"}
          </div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 9px; color: rgba(0,0,0,0.6); margin-bottom: 8px;">
            <div>Capacity: <b style="color:#000">${asset.capacity_mva || 40} MVA</b></div>
            <div>Voltage: <b style="color:#000">${asset.voltage_kv || 66} kV</b></div>
            <div>Risk Score: <b style="color:${color}">${Math.round(asset.overall_risk_score || 50)}%</b></div>
            <div>Consumers: <b style="color:#000">${(asset.customers_served || 0).toLocaleString()}</b></div>
          </div>
          <div style="font-size: 9px; color: #00754A; font-weight: 700; text-transform: uppercase; text-align: center; border-top: 1px solid #e7e5e0; padding-top: 6px; cursor: pointer;">
            Selected in Telemetry Inspector &bull; Active
          </div>
        </div>
      </div>
    `;
  }, []);

  // Initialize Map with Google Maps Physics & Kinetic Smoothness
  useEffect(() => {
    if (!containerRef.current) return;

    if (mapInstanceRef.current) {
      mapInstanceRef.current.remove();
      mapInstanceRef.current = null;
    }

    if ((containerRef.current as any)._leaflet_id != null) {
      (containerRef.current as any)._leaflet_id = null;
    }

    let isMounted = true;

    import("leaflet").then((leafletModule) => {
      if (!isMounted || !containerRef.current) return;
      const L = leafletModule.default || leafletModule;

      delete (L.Icon.Default.prototype as any)._getIconUrl;

      // Initialize Leaflet with Google Maps-type swipe and kinetic glide physics
      const map = L.map(containerRef.current, {
        center: [22.8, 71.5], // Gujarat Geographical Center
        zoom: 7.5,
        minZoom: 6,
        maxZoom: 18,
        zoomControl: false, // Sleek custom Starbucks zoom controls
        attributionControl: false,
        preferCanvas: true, // Forces GPU Canvas acceleration for 60fps rendering
        // Kinetic momentum & smooth swiping:
        inertia: true,
        inertiaDeceleration: 1500, // Smooth glide rather than sudden stop
        inertiaMaxSpeed: 2800, // Responsive high-speed swipe
        easeLinearity: 0.12, // Smooth ease curve
        zoomSnap: 0.25, // Fractional zoom for smooth trackpad & pinch gestures
        zoomDelta: 0.5,
        wheelDebounceTime: 25,
        wheelPxPerZoomLevel: 90,
        fadeAnimation: true,
        zoomAnimation: true,
        markerZoomAnimation: true,
        bounceAtZoomLimits: false,
      });

      mapInstanceRef.current = map;

      // High performance Canvas renderer for all markers and transmission lines
      const canvasRenderer = L.canvas({ padding: 0.5, tolerance: 8 });
      canvasRendererRef.current = canvasRenderer;

      // Fast tile layer with generous GPU pre-buffering (keepBuffer: 8) so panning is instantaneous
      const styleConfig = TILE_STYLES[currentStyle];
      const baseTile = L.tileLayer(styleConfig.url, {
        maxZoom: styleConfig.maxZoom,
        tileSize: 256,
        subdomains: styleConfig.subdomains || ["a", "b", "c"],
        keepBuffer: 8, // Pre-caches 8 tile rings so moving up/down has no blank tiles
        updateWhenIdle: false, // Continuously updates during smooth panning
        updateWhenZooming: false,
        updateInterval: 50,
      }).addTo(map);

      tileLayerRef.current = baseTile;

      // Layer groups
      const linesGroup = L.layerGroup().addTo(map);
      linesLayerRef.current = linesGroup;

      const markersGroup = L.layerGroup().addTo(map);
      markersLayerRef.current = markersGroup;

      const selectedGroup = L.layerGroup().addTo(map);
      selectedMarkerLayerRef.current = selectedGroup;

      // Render content
      renderCanvasLayers(L, map, canvasRenderer, markersGroup, linesGroup, selectedGroup, markers, selectedRef.current, showPowerLines, transmissionLines);

      // Invalidate layout dimensions safely
      setTimeout(() => {
        if (mapInstanceRef.current) mapInstanceRef.current.invalidateSize();
      }, 200);

      const handleResize = () => {
        if (mapInstanceRef.current) mapInstanceRef.current.invalidateSize();
      };
      window.addEventListener("resize", handleResize);
    });

    return () => {
      isMounted = false;
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
      if (containerRef.current) {
        (containerRef.current as any)._leaflet_id = null;
      }
    };
  }, []);

  // Switch Tile Theme
  const changeTileStyle = (styleKey: string) => {
    setCurrentStyle(styleKey);
    const styleConfig = TILE_STYLES[styleKey];
    if (tileLayerRef.current && styleConfig) {
      tileLayerRef.current.setUrl(styleConfig.url);
      if (styleConfig.subdomains) {
        tileLayerRef.current.options.subdomains = styleConfig.subdomains;
      }
    }
  };

  // Render High-Performance GPU Canvas Markers and Transmission Lines
  const renderCanvasLayers = (
    L: any,
    map: any,
    renderer: any,
    markersGroup: any,
    linesGroup: any,
    selectedGroup: any,
    items: typeof markers,
    selectedId: string | undefined,
    drawLines: boolean,
    linesData: Array<[[number, number], [number, number]]>
  ) => {
    if (!markersGroup || !linesGroup || !selectedGroup || !renderer) return;

    markersGroup.clearLayers();
    linesGroup.clearLayers();
    selectedGroup.clearLayers();

    if (!items || items.length === 0) return;

    // 1. Draw transmission lines directly onto the GPU Canvas
    if (drawLines && linesData.length > 0) {
      linesData.forEach((coords) => {
        const polyline = L.polyline(coords, {
          renderer: renderer,
          color: "#00754A",
          weight: 1.6,
          opacity: 0.5,
          dashArray: "4, 6",
        });
        linesGroup.addLayer(polyline);
      });
    }

    // 2. Render all 836 assets as GPU Canvas CircleMarkers (60 FPS Locked)
    let selectedAssetObj: any = null;

    items.forEach((asset) => {
      if (!asset.latitude || !asset.longitude) return;

      const risk = (asset.risk_level || "MEDIUM").toUpperCase();
      const color =
        risk === "CRITICAL"
          ? "#c82014"
        : risk === "HIGH"
        ? "#e67e22"
        : risk === "MEDIUM"
        ? "#cba258"
        : "#00754A";

      const isPowerPlant = asset.asset_type === "power_plant" || asset.asset_id.startsWith("PP-");
      const isSubstation = asset.asset_type === "substation" || asset.asset_id.startsWith("SS-");
      const isSelected = selectedId === asset.asset_id;

      if (isSelected) {
        selectedAssetObj = asset;
      }

      const radius = isPowerPlant ? 9 : isSubstation ? 6.5 : 4.5;
      const weight = isPowerPlant ? 2.5 : 1.5;

      // CircleMarker drawn directly on GPU Canvas with zero DOM layout cost!
      const circle = L.circleMarker([asset.latitude, asset.longitude], {
        renderer: renderer,
        radius: radius,
        fillColor: color,
        color: "#ffffff",
        weight: weight,
        opacity: 1,
        fillOpacity: 0.92,
      });

      // Interactive Click on Canvas
      circle.on("click", (e: any) => {
        if (onSelectRef.current) {
          onSelectRef.current(asset.asset_id);
        }
        L.popup({
          offset: [0, -radius],
          closeButton: false,
          className: "custom-leaflet-popup",
        })
          .setLatLng(e.latlng)
          .setContent(buildPopupContent(asset))
          .openOn(map);
      });

      // Hover tooltip for quick glance
      circle.bindTooltip(`<b>${asset.asset_id}</b> &bull; ${asset.name || asset.district}`, {
        direction: "top",
        offset: [0, -radius],
        className: "custom-leaflet-tooltip",
      });

      markersGroup.addLayer(circle);
    });

    // 3. Render Focused Beacon Ring on Selected Asset
    if (selectedAssetObj && selectedAssetObj.latitude && selectedAssetObj.longitude) {
      const beaconIcon = L.divIcon({
        className: "selected-beacon-icon",
        html: `
          <div style="position: relative; width: 34px; height: 34px; display: flex; align-items: center; justify-content: center; pointer-events: none;">
            <div style="position: absolute; width: 34px; height: 34px; border-radius: 50%; background: rgba(0, 117, 74, 0.25); animation: beaconPulse 1.8s infinite;"></div>
            <div style="position: absolute; width: 20px; height: 20px; border-radius: 50%; border: 3px solid #1E3932; box-shadow: 0 0 10px rgba(0,0,0,0.5);"></div>
          </div>
        `,
        iconSize: [34, 34],
        iconAnchor: [17, 17],
      });

      const beaconMarker = L.marker([selectedAssetObj.latitude, selectedAssetObj.longitude], {
        icon: beaconIcon,
        zIndexOffset: 2000,
      });
      selectedGroup.addLayer(beaconMarker);
    }
  };

  // Fly to asset and open popup when selectedAssetId updates
  useEffect(() => {
    if (!mapInstanceRef.current || !selectedAssetId) return;
    const target = markers.find((m) => m.asset_id === selectedAssetId);
    if (target && target.latitude && target.longitude) {
      mapInstanceRef.current.flyTo([target.latitude, target.longitude], 12.5, {
        duration: 1.0,
        easeLinearity: 0.15,
      });

      import("leaflet").then((leafletModule) => {
        const L = leafletModule.default || leafletModule;
        setTimeout(() => {
          if (!mapInstanceRef.current) return;
          L.popup({
            offset: [0, -8],
            closeButton: false,
            className: "custom-leaflet-popup",
          })
            .setLatLng([target.latitude, target.longitude])
            .setContent(buildPopupContent(target))
            .openOn(mapInstanceRef.current);
        }, 500);
      });
    }
  }, [selectedAssetId, markers, buildPopupContent]);

  // Update canvas markers when markers, selectedAssetId, or lines toggle change
  useEffect(() => {
    if (!mapInstanceRef.current || !markersLayerRef.current || !canvasRendererRef.current) return;
    import("leaflet").then((leafletModule) => {
      const L = leafletModule.default || leafletModule;
      renderCanvasLayers(
        L,
        mapInstanceRef.current,
        canvasRendererRef.current,
        markersLayerRef.current,
        linesLayerRef.current,
        selectedMarkerLayerRef.current,
        markers,
        selectedAssetId,
        showPowerLines,
        transmissionLines
      );
    });
  }, [markers, selectedAssetId, showPowerLines, transmissionLines]);

  // Zoom In / Out Handlers
  const handleZoomIn = () => {
    if (mapInstanceRef.current) mapInstanceRef.current.zoomIn();
  };

  const handleZoomOut = () => {
    if (mapInstanceRef.current) mapInstanceRef.current.zoomOut();
  };

  const handleResetView = () => {
    if (mapInstanceRef.current) {
      mapInstanceRef.current.flyTo([22.8, 71.5], 7.5, { duration: 1.0 });
    }
  };

  return (
    <div className="w-full h-full relative bg-[#edebe9] overflow-hidden select-none" style={{ minHeight: "100%", width: "100%" }}>
      <style jsx global>{`
        @keyframes beaconPulse {
          0% {
            transform: scale(0.6);
            opacity: 0.9;
          }
          70% {
            transform: scale(1.6);
            opacity: 0;
          }
          100% {
            transform: scale(0.6);
            opacity: 0;
          }
        }
        .custom-leaflet-popup .leaflet-popup-content-wrapper {
          background: transparent !important;
          padding: 0 !important;
          border-radius: 12px !important;
          box-shadow: none !important;
        }
        .custom-leaflet-popup .leaflet-popup-content {
          margin: 0 !important;
          line-height: normal !important;
        }
        .custom-leaflet-popup .leaflet-popup-tip {
          background: #ffffff !important;
          border: 1px solid #e7e5e0 !important;
        }
        .custom-leaflet-tooltip {
          background: #1E3932 !important;
          color: #ffffff !important;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
          font-size: 10px !important;
          padding: 4px 8px !important;
          border-radius: 50px !important;
          border: 1px solid #00754A !important;
          box-shadow: 0 4px 12px rgba(0,0,0,0.18) !important;
        }
        .custom-leaflet-tooltip:before {
          border-top-color: #1E3932 !important;
        }
        .leaflet-container {
          background: #edebe9 !important;
          font-family: inherit !important;
          cursor: grab !important;
        }
        .leaflet-container:active {
          cursor: grabbing !important;
        }
      `}</style>

      {/* TOP-RIGHT CONTROLS: TILE THEMES & GRID LINES */}
      <div className="absolute top-3 right-3 z-[1000] flex items-center gap-1.5 bg-white/95 border border-[#e7e5e0] p-1.5 rounded-full shadow-md backdrop-blur-md">
        <span className="text-[10px] text-[#1E3932] font-bold uppercase px-2">Theme:</span>
        <button
          onClick={() => changeTileStyle("voyager")}
          className={`px-3 py-1 text-[10px] font-bold uppercase rounded-full transition-all active:scale-95 ${
            currentStyle === "voyager" ? "bg-[#00754A] text-white shadow-xs" : "bg-transparent text-gray-700 hover:bg-[#f2f0eb]"
          }`}
        >
          Cream
        </button>
        <button
          onClick={() => changeTileStyle("dataviz")}
          className={`px-3 py-1 text-[10px] font-bold uppercase rounded-full transition-all active:scale-95 ${
            currentStyle === "dataviz" ? "bg-[#00754A] text-white shadow-xs" : "bg-transparent text-gray-700 hover:bg-[#f2f0eb]"
          }`}
        >
          Dark
        </button>
        <button
          onClick={() => changeTileStyle("hybrid")}
          className={`px-3 py-1 text-[10px] font-bold uppercase rounded-full transition-all active:scale-95 ${
            currentStyle === "hybrid" ? "bg-[#00754A] text-white shadow-xs" : "bg-transparent text-gray-700 hover:bg-[#f2f0eb]"
          }`}
        >
          Satellite
        </button>
        <button
          onClick={() => changeTileStyle("streets")}
          className={`px-3 py-1 text-[10px] font-bold uppercase rounded-full transition-all active:scale-95 ${
            currentStyle === "streets" ? "bg-[#00754A] text-white shadow-xs" : "bg-transparent text-gray-700 hover:bg-[#f2f0eb]"
          }`}
        >
          Highways
        </button>
        <button
          onClick={() => setShowPowerLines(!showPowerLines)}
          className={`px-3 py-1 text-[10px] font-bold uppercase rounded-full border transition-all active:scale-95 ${
            showPowerLines ? "bg-[#d4e9e2] text-[#006241] border-[#00754A]" : "text-gray-500 border-gray-300"
          }`}
        >
          ⚡ Grid: {showPowerLines ? "ON" : "OFF"}
        </button>
      </div>

      {/* BOTTOM-RIGHT GOOGLE MAPS STYLE SMOOTH ZOOM & RECENTER CONTROLS */}
      <div className="absolute bottom-4 right-4 z-[1000] flex flex-col gap-1.5">
        <div className="bg-white/95 border border-[#e7e5e0] rounded-xl shadow-md p-1 flex flex-col backdrop-blur-md">
          <button
            onClick={handleZoomIn}
            className="w-8 h-8 flex items-center justify-center font-bold text-gray-700 hover:bg-[#f2f0eb] rounded-lg transition-all active:scale-95 text-base cursor-pointer"
            title="Zoom in (Google Maps style)"
          >
            +
          </button>
          <div className="w-full h-px bg-gray-200 my-0.5" />
          <button
            onClick={handleZoomOut}
            className="w-8 h-8 flex items-center justify-center font-bold text-gray-700 hover:bg-[#f2f0eb] rounded-lg transition-all active:scale-95 text-base cursor-pointer"
            title="Zoom out (Google Maps style)"
          >
            &minus;
          </button>
        </div>

        <button
          onClick={handleResetView}
          className="bg-white/95 border border-[#e7e5e0] text-[#1E3932] px-2.5 py-1.5 rounded-xl shadow-md text-[10px] font-bold hover:bg-[#f2f0eb] transition-all active:scale-95 cursor-pointer backdrop-blur-md flex items-center gap-1 justify-center"
          title="Recenter to Gujarat Geographic Center"
        >
          🎯 Gujarat
        </button>
      </div>

      {/* MAP MOUNT CONTAINER */}
      <div
        ref={containerRef}
        className="w-full h-full"
        style={{ width: "100%", height: "100%", position: "absolute", top: 0, left: 0 }}
      />
    </div>
  );
}
