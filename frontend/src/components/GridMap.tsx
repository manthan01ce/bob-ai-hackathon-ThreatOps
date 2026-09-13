"use client";

import React, { useEffect, useRef, useState } from "react";
import "leaflet/dist/leaflet.css";

const MAPTILER_KEY = "CRFoY3RXgAloQLarTcRL";

// Tile Styles
const TILE_STYLES: Record<string, { name: string; url: string; subdomains?: string[] }> = {
  dataviz: {
    name: "Dark SCADA",
    url: `https://api.maptiler.com/maps/dataviz-dark/256/{z}/{x}/{y}.png?key=${MAPTILER_KEY}`,
  },
  hybrid: {
    name: "Satellite Hybrid",
    url: `https://api.maptiler.com/maps/hybrid/256/{z}/{x}/{y}.jpg?key=${MAPTILER_KEY}`,
  },
  streets: {
    name: "Highways & Grid",
    url: `https://api.maptiler.com/maps/streets-v2-dark/256/{z}/{x}/{y}.png?key=${MAPTILER_KEY}`,
  },
};

const riskColor: Record<string, string> = {
  CRITICAL: "#e22718",
  HIGH: "#f48c06",
  MEDIUM: "#f4b400",
  LOW: "#0fa336",
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
  const markersLayerRef = useRef<any>(null);
  const linesLayerRef = useRef<any>(null);
  const tileLayerRef = useRef<any>(null);
  const [currentStyle, setCurrentStyle] = useState<string>("dataviz");
  const [showPowerLines, setShowPowerLines] = useState<boolean>(true);

  const onSelectRef = useRef(onSelectAsset);
  onSelectRef.current = onSelectAsset;

  const selectedRef = useRef(selectedAssetId);
  selectedRef.current = selectedAssetId;

  // Initialize Map safely (fixing "Map container is already initialized" error)
  useEffect(() => {
    if (!containerRef.current) return;

    // Destroy existing leaflet instance attached to DOM element
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

      const map = L.map(containerRef.current, {
        center: [22.8, 71.5], // Gujarat Geographical Center
        zoom: 7.5,
        minZoom: 6,
        maxZoom: 18,
        zoomControl: true,
        attributionControl: false,
      });

      mapInstanceRef.current = map;

      // Base Tile Layer with Carto Dark fallback
      const baseTile = L.tileLayer(TILE_STYLES[currentStyle].url, {
        maxZoom: 19,
        tileSize: 256,
        errorTileUrl: "https://a.basemaps.cartocdn.com/dark_all/0/0/0.png",
      }).addTo(map);

      tileLayerRef.current = baseTile;

      baseTile.on("tileerror", () => {
        baseTile.setUrl("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png");
      });

      // Layer for Transmission Lines
      const linesGroup = L.layerGroup().addTo(map);
      linesLayerRef.current = linesGroup;

      // Layer for Equipment Markers
      const markersGroup = L.layerGroup().addTo(map);
      markersLayerRef.current = markersGroup;

      // Render assets and interconnecting transmission grid lines
      renderMapContent(L, markersGroup, linesGroup, markers, selectedRef.current, showPowerLines);

      // Invalidate layout dimensions safely
      setTimeout(() => {
        if (mapInstanceRef.current) mapInstanceRef.current.invalidateSize();
      }, 250);

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

  // Switch Tile Theme (Satellite Hybrid vs Dark SCADA)
  const changeTileStyle = (styleKey: string) => {
    setCurrentStyle(styleKey);
    if (tileLayerRef.current) {
      tileLayerRef.current.setUrl(TILE_STYLES[styleKey].url);
    }
  };

  const markersMapRef = useRef<Record<string, any>>({});

  // Fly to asset and open popup whenever selectedAssetId changes (Fixes "row to focus does nothing")
  useEffect(() => {
    if (!mapInstanceRef.current || !selectedAssetId) return;
    const target = markers.find((m) => m.asset_id === selectedAssetId);
    if (target && target.latitude && target.longitude) {
      mapInstanceRef.current.flyTo([target.latitude, target.longitude], 12.5, {
        duration: 1.2,
      });
      const marker = markersMapRef.current[selectedAssetId];
      if (marker) {
        setTimeout(() => {
          try {
            marker.openPopup();
          } catch (e) {}
        }, 500);
      }
    }
  }, [selectedAssetId, markers]);

  // Render Markers & Grid Interconnect Lines
  const renderMapContent = (
    L: any,
    markersGroup: any,
    linesGroup: any,
    items: typeof markers,
    selectedId?: string,
    drawLines = true
  ) => {
    if (!markersGroup || !linesGroup) return;
    markersGroup.clearLayers();
    linesGroup.clearLayers();
    markersMapRef.current = {};

    if (!items || items.length === 0) return;

    // 1. Separate Substations / Power Plants for Transmission Interconnects
    const substations = items.filter(
      (a) =>
        a.asset_type === "substation" ||
        a.asset_type === "power_plant" ||
        a.asset_id.startsWith("SS-") ||
        a.asset_id.startsWith("PP-")
    );

    // 2. Draw High Voltage Grid Transmission Lines between Substations
    if (drawLines && substations.length > 1) {
      // Connect geographically nearest substations to simulate GETCO 400kV / 220kV Grid
      for (let i = 0; i < substations.length; i++) {
        const s1 = substations[i];
        if (!s1.latitude || !s1.longitude) continue;

        // Find 2 nearest neighbors
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
            const line = L.polyline(
              [
                [s1.latitude, s1.longitude],
                [s2.latitude, s2.longitude],
              ],
              {
                color: "#00754A",
                weight: 1.8,
                opacity: 0.55,
                dashArray: "5, 6",
              }
            );
            linesGroup.addLayer(line);
          }
        });
      }
    }

    // 3. Render Custom Industrial Markers
    items.forEach((asset) => {
      if (!asset.latitude || !asset.longitude) return;

      const risk = (asset.risk_level || "MEDIUM").toUpperCase();
      const color = risk === "CRITICAL" ? "#c82014" : risk === "HIGH" ? "#e67e22" : risk === "MEDIUM" ? "#cba258" : "#00754A";
      const isSelected = selectedId === asset.asset_id;
      const isPowerPlant = asset.asset_type === "power_plant" || asset.asset_id.startsWith("PP-");
      const isSubstation = asset.asset_type === "substation" || asset.asset_id.startsWith("SS-");
      const isCritical = risk === "CRITICAL";

      let shapeStyles = "border-radius: 50%;";
      let size = isSelected ? 22 : 11;
      let symbolText = "";

      if (isPowerPlant) {
        shapeStyles = "border-radius: 4px; transform: rotate(0deg);";
        size = isSelected ? 26 : 16;
        symbolText = "⚡";
      } else if (isSubstation) {
        shapeStyles = "border-radius: 3px; transform: rotate(45deg);";
        size = isSelected ? 22 : 13;
      }

      const html = `
        <div class="custom-grid-marker ${isCritical ? "marker-critical-pulse" : ""} ${isSelected ? "marker-selected" : ""}" 
             style="width: ${size}px; height: ${size}px; background: ${color}; ${shapeStyles} 
                    border: ${isSelected ? "3px solid #1E3932" : "2px solid #ffffff"}; 
                    box-shadow: 0 0 ${isSelected ? "18px" : isPowerPlant ? "10px" : "5px"} ${color}; 
                    display: flex; align-items: center; justify-content: center; font-size: 10px; cursor: pointer; color: #fff;">
          ${symbolText}
        </div>
      `;

      const icon = L.divIcon({
        className: "leaflet-grid-div-icon",
        html: html,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
      });

      const marker = L.marker([asset.latitude, asset.longitude], { icon: icon });
      markersMapRef.current[asset.asset_id] = marker;

      // Starbucks Themed Inspector Popup (House Green Header, Cream/White Card Body)
      const popupHtml = `
        <div style="background: #ffffff; color: rgba(0,0,0,0.87); border-radius: 12px; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 11px; border: 1px solid #e7e5e0; min-width: 190px; box-shadow: 0 8px 24px rgba(0,0,0,0.18);">
          <div style="background: #1E3932; color: #ffffff; padding: 10px 12px; display: flex; align-items: center; justify-content: space-between;">
            <div>
              <div style="font-weight: 700; font-size: 13px; letter-spacing: -0.01em;">${asset.asset_id}</div>
              <div style="font-size: 9px; color: rgba(255,255,255,0.7); text-transform: uppercase;">
                ${isPowerPlant ? "🏭 Power Plant" : isSubstation ? "⚡ GETCO Substation" : "🔌 Distribution Transformer"}
              </div>
            </div>
            <span style="background: ${color}; color: #ffffff; font-weight: 700; font-size: 9px; padding: 2px 7px; border-radius: 50px; text-transform: uppercase;">
              ${risk}
            </span>
          </div>
          <div style="padding: 10px 12px; background: #faf9f6;">
            <div style="color: rgba(0,0,0,0.7); font-size: 10px; margin-bottom: 6px; font-weight: 600;">
              ${asset.name || "Gujarat Power Grid"} &bull; ${asset.district || "Gujarat"}
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; font-size: 9px; color: rgba(0,0,0,0.6); margin-bottom: 8px;">
              <div>Capacity: <b style="color:#000">${asset.capacity_mva || 40} MVA</b></div>
              <div>Voltage: <b style="color:#000">${asset.voltage_kv || 66} kV</b></div>
              <div>Risk Score: <b style="color:${color}">${Math.round(asset.overall_risk_score || 50)}%</b></div>
              <div>Consumers: <b style="color:#000">${(asset.customers_served || 0).toLocaleString()}</b></div>
            </div>
            <div style="font-size: 9px; color: #00754A; font-weight: 700; text-transform: uppercase; text-align: center; border-top: 1px solid #e7e5e0; padding-top: 6px; cursor: pointer;">
              Click to inspect &rarr;
            </div>
          </div>
        </div>
      `;

      marker.bindPopup(popupHtml, {
        offset: [0, -size / 2],
        closeButton: false,
        className: "custom-leaflet-popup",
      });

      marker.on("click", () => {
        if (onSelectRef.current) {
          onSelectRef.current(asset.asset_id);
        }
      });

      marker.on("mouseover", function (this: any) {
        this.openPopup();
      });

      markersGroup.addLayer(marker);
    });
  };

  // Update markers when props change
  useEffect(() => {
    if (!mapInstanceRef.current || !markersLayerRef.current) return;
    import("leaflet").then((leafletModule) => {
      const L = leafletModule.default || leafletModule;
      renderMapContent(L, markersLayerRef.current, linesLayerRef.current, markers, selectedAssetId, showPowerLines);
    });
  }, [markers, selectedAssetId, showPowerLines]);

  return (
    <div className="w-full h-full relative bg-[#edebe9] overflow-hidden" style={{ minHeight: "100%", width: "100%" }}>
      <style jsx global>{`
        @keyframes criticalPulse {
          0% {
            box-shadow: 0 0 0 0 rgba(200, 32, 20, 0.8), 0 0 8px #c82014;
          }
          70% {
            box-shadow: 0 0 0 14px rgba(200, 32, 20, 0), 0 0 12px #c82014;
          }
          100% {
            box-shadow: 0 0 0 0 rgba(200, 32, 20, 0), 0 0 8px #c82014;
          }
        }
        .marker-critical-pulse {
          animation: criticalPulse 1.8s infinite !important;
        }
        .marker-selected {
          transform: scale(1.35) !important;
          z-index: 1000 !important;
        }
        .leaflet-grid-div-icon {
          background: transparent !important;
          border: none !important;
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
        .leaflet-container {
          background: #edebe9 !important;
          font-family: inherit !important;
        }
      `}</style>

      {/* Floating Starbucks Pill Map Controls */}
      <div className="absolute top-3 right-3 z-[1000] flex items-center gap-1.5 bg-white/95 border border-[#e7e5e0] p-1.5 rounded-full shadow-md backdrop-blur-md">
        <span className="text-[10px] text-[#1E3932] font-bold uppercase px-2">Map:</span>
        <button
          onClick={() => changeTileStyle("dataviz")}
          className={`px-3 py-1 text-[10px] font-bold uppercase rounded-full transition-all active:scale-95 ${
            currentStyle === "dataviz" ? "bg-[#00754A] text-white" : "bg-transparent text-gray-700 hover:bg-[#f2f0eb]"
          }`}
        >
          SCADA
        </button>
        <button
          onClick={() => changeTileStyle("hybrid")}
          className={`px-3 py-1 text-[10px] font-bold uppercase rounded-full transition-all active:scale-95 ${
            currentStyle === "hybrid" ? "bg-[#00754A] text-white" : "bg-transparent text-gray-700 hover:bg-[#f2f0eb]"
          }`}
        >
          Satellite
        </button>
        <button
          onClick={() => changeTileStyle("streets")}
          className={`px-3 py-1 text-[10px] font-bold uppercase rounded-full transition-all active:scale-95 ${
            currentStyle === "streets" ? "bg-[#00754A] text-white" : "bg-transparent text-gray-700 hover:bg-[#f2f0eb]"
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

      <div
        ref={containerRef}
        className="w-full h-full"
        style={{ width: "100%", height: "100%", position: "absolute", top: 0, left: 0 }}
      />
    </div>
  );
}

