import { useEffect, useRef, useState } from 'react';
import Modal from '../Modal.jsx';
import { Field, TextInput, PrimaryButton, GhostButton } from '../Field.jsx';
import { api } from '../../services/api.js';

// Must match backend Settings.reference_adult_height_cm — the assumed
// average adult height that a calibration reference_height_px represents.
const REFERENCE_ADULT_HEIGHT_CM = 165;
const FEET_TO_CM = 30.48;

export default function CameraConfigModal({ open, onClose, camera }) {
  const [mode, setMode] = useState('roi');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  const [roiPoints, setRoiPoints] = useState([]);
  const [calibrationPoints, setCalibrationPoints] = useState([]);
  const [adultRatio, setAdultRatio] = useState('1.0');
  const [childRatio, setChildRatio] = useState('0.56');
  const [pendingCalibClicks, setPendingCalibClicks] = useState([]);
  const [pendingRealHeightFeet, setPendingRealHeightFeet] = useState('5.5');
  const [gateLine, setGateLine] = useState([]);
  const [gateInside, setGateInside] = useState(null);

  const canvasRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    api
      .getCameraConfiguration(camera.id)
      .then((cfg) => {
        if (cancelled) return;
        setRoiPoints(cfg.roi ?? []);
        setCalibrationPoints(cfg.calibration_points ?? []);
        setAdultRatio(String(cfg.adult_height_ratio ?? 1.0));
        setChildRatio(String(cfg.child_height_ratio ?? 0.6));
        setGateLine(cfg.gate_line ?? []);
        setGateInside(cfg.gate_inside_point ?? null);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, camera.id]);

  // Native (camera resolution) <-> display (rendered canvas pixels) scaling.
  const toDisplay = (native) => {
    const el = canvasRef.current;
    if (!el) return native;
    return {
      x: (native.x / camera.resolution_width) * el.clientWidth,
      y: (native.y / camera.resolution_height) * el.clientHeight,
    };
  };
  const toNative = (display) => {
    const el = canvasRef.current;
    if (!el) return display;
    return {
      x: (display.x / el.clientWidth) * camera.resolution_width,
      y: (display.y / el.clientHeight) * camera.resolution_height,
    };
  };

  const draw = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.width = canvas.clientWidth;
    canvas.height = canvas.clientHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (roiPoints.length > 0) {
      const pts = roiPoints.map(toDisplay);
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      pts.slice(1).forEach((p) => ctx.lineTo(p.x, p.y));
      if (pts.length > 2) ctx.closePath();
      ctx.strokeStyle = '#2451e0';
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.fillStyle = 'rgba(36,81,224,0.15)';
      if (pts.length > 2) ctx.fill();
      pts.forEach((p) => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
        ctx.fillStyle = '#2451e0';
        ctx.fill();
      });
    }

    calibrationPoints.forEach((cp) => {
      const y = toDisplay({ x: 0, y: cp.pixel_y }).y;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(canvas.width, y);
      ctx.strokeStyle = '#b4790c';
      ctx.lineWidth = 1;
      ctx.setLineDash([6, 4]);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = '#b4790c';
      ctx.font = '11px sans-serif';
      ctx.fillText(`${cp.reference_height_px}px ref`, 6, y - 4);
    });

    if (pendingCalibClicks.length > 0) {
      const pts = pendingCalibClicks.map(toDisplay);
      pts.forEach((p, i) => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
        ctx.fillStyle = '#1a9d5c';
        ctx.fill();
        ctx.font = '11px sans-serif';
        ctx.fillStyle = '#1a9d5c';
        ctx.fillText(i === 0 ? 'feet' : 'head', p.x + 8, p.y + 4);
      });
      if (pts.length === 2) {
        ctx.beginPath();
        ctx.moveTo(pts[0].x, pts[0].y);
        ctx.lineTo(pts[1].x, pts[1].y);
        ctx.strokeStyle = '#1a9d5c';
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }

    if (gateLine.length > 0) {
      const pts = gateLine.map(toDisplay);
      if (pts.length === 2) {
        ctx.beginPath();
        ctx.moveTo(pts[0].x, pts[0].y);
        ctx.lineTo(pts[1].x, pts[1].y);
        ctx.strokeStyle = '#d3402e';
        ctx.lineWidth = 3;
        ctx.stroke();
      }
      pts.forEach((p) => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
        ctx.fillStyle = '#d3402e';
        ctx.fill();
      });
    }
    if (gateInside) {
      const p = toDisplay(gateInside);
      ctx.beginPath();
      ctx.arc(p.x, p.y, 6, 0, Math.PI * 2);
      ctx.fillStyle = '#1a9d5c';
      ctx.fill();
      ctx.font = '11px sans-serif';
      ctx.fillStyle = '#1a9d5c';
      ctx.fillText('inside', p.x + 8, p.y + 4);
    }
  };

  useEffect(draw); // redraw on every render — cheap 2D canvas, keeps state/draw in lockstep

  useEffect(() => {
    const onResize = () => draw();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onCanvasClick = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const display = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    const native = toNative(display);
    if (mode === 'roi') {
      setRoiPoints((prev) => [...prev, native]);
    } else if (mode === 'gate') {
      if (gateLine.length < 2) {
        setGateLine((prev) => [...prev, native]);
      } else if (!gateInside) {
        setGateInside(native);
      }
    } else if (mode === 'calibration') {
      setPendingCalibClicks((prev) => (prev.length < 2 ? [...prev, native] : prev));
    }
  };

  const saveRoi = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await api.saveRoi(camera.id, { roi: roiPoints });
      setMessage('ROI saved.');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Failed to save ROI');
    } finally {
      setSaving(false);
    }
  };

  const saveCalibration = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await api.saveCalibration(camera.id, {
        calibration_points: calibrationPoints,
        adult_height_ratio: Number(adultRatio) || undefined,
        child_height_ratio: Number(childRatio) || undefined,
      });
      setMessage('Calibration saved.');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Failed to save calibration');
    } finally {
      setSaving(false);
    }
  };

  const saveGate = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await api.saveGateLine(camera.id, { gate_line: gateLine, gate_inside_point: gateInside });
      setMessage('Gate line saved.');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Failed to save gate line');
    } finally {
      setSaving(false);
    }
  };

  const addCalibrationRow = () => {
    if (pendingCalibClicks.length !== 2) return;
    const realHeightFeet = Number(pendingRealHeightFeet);
    if (!realHeightFeet || realHeightFeet <= 0) return;
    const [feetPoint, headPoint] = pendingCalibClicks;
    const measuredPx = Math.abs(headPoint.y - feetPoint.y);
    const realHeightCm = realHeightFeet * FEET_TO_CM;
    const referenceHeightPx = Math.round(measuredPx * (REFERENCE_ADULT_HEIGHT_CM / realHeightCm));
    setCalibrationPoints((prev) => [...prev, { pixel_y: Math.round(feetPoint.y), reference_height_px: referenceHeightPx }]);
    setPendingCalibClicks([]);
  };

  const tabBtn = (key, label) => (
    <button
      onClick={() => setMode(key)}
      className="px-3 py-1.5 rounded-lg text-sm"
      style={{
        background: mode === key ? 'var(--brand)' : 'var(--neutral-bg)',
        color: mode === key ? '#fff' : 'var(--ink-soft)',
      }}
    >
      {label}
    </button>
  );

  return (
    <Modal open={open} onClose={onClose} title={`Configure — ${camera.name}`} width={860}>
      <div className="mb-3 flex gap-2">
        {tabBtn('roi', 'Region of Interest')}
        {tabBtn('calibration', 'Height Calibration')}
        {tabBtn('gate', 'Gate Line')}
      </div>

      {loading ? (
        <div className="flex justify-center py-10 text-sm" style={{ color: 'var(--ink-faint)' }}>Loading…</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-4">
          <div
            className="relative overflow-hidden rounded-lg bg-black"
            style={{ aspectRatio: `${camera.resolution_width} / ${camera.resolution_height}` }}
          >
            <img src={api.streamUrl(camera.id)} alt={camera.name} className="absolute inset-0 h-full w-full object-contain" />
            <canvas ref={canvasRef} className="absolute inset-0 h-full w-full cursor-crosshair" onClick={onCanvasClick} />
          </div>

          <div className="flex flex-col gap-3">
            {mode === 'roi' ? (
              <>
                <p className="text-xs" style={{ color: 'var(--ink-faint)' }}>
                  Click on the image to add polygon points ({roiPoints.length} point{roiPoints.length === 1 ? '' : 's'}).
                  Coordinates are scaled to the camera's native {camera.resolution_width}×{camera.resolution_height} resolution.
                </p>
                <div className="flex gap-2">
                  <GhostButton className="flex-1" onClick={() => setRoiPoints([])}>Reset</GhostButton>
                  <PrimaryButton className="flex-1" disabled={saving} onClick={saveRoi}>Save ROI</PrimaryButton>
                </div>
              </>
            ) : mode === 'gate' ? (
              <>
                <p className="text-xs" style={{ color: 'var(--ink-faint)' }}>
                  Click 2 points to draw the gate/entrance line, then a 3rd point anywhere clearly inside the
                  classroom (green) to mark which side is "inside." A tracked person is only counted as entering
                  when they cross this line from outside to inside.
                </p>
                <p className="text-xs" style={{ color: 'var(--ink-faint)' }}>
                  Line points: {gateLine.length}/2 {gateInside ? '· inside point set' : ''}
                </p>
                <div className="flex gap-2">
                  <GhostButton className="flex-1" onClick={() => { setGateLine([]); setGateInside(null); }}>Reset</GhostButton>
                  <PrimaryButton className="flex-1" disabled={saving || gateLine.length !== 2 || !gateInside} onClick={saveGate}>
                    Save gate line
                  </PrimaryButton>
                </div>
              </>
            ) : (
              <>
                <p className="text-xs" style={{ color: 'var(--ink-faint)' }}>
                  Have someone (or something) of a known height stand where you want to calibrate. Click their
                  feet, then the top of their head — the pixel height is measured automatically. Enter the real
                  height (feet — doesn't have to be an adult).
                </p>
                {pendingCalibClicks.length > 0 && (
                  <div className="flex flex-col gap-2 rounded-lg border p-2" style={{ borderColor: 'var(--line)' }}>
                    {pendingCalibClicks.length === 1 ? (
                      <p className="text-xs">Feet marked at row {Math.round(pendingCalibClicks[0].y)}. Now click the top of their head.</p>
                    ) : (
                      <>
                        <p className="text-xs">
                          Measured: <b>{Math.round(Math.abs(pendingCalibClicks[1].y - pendingCalibClicks[0].y))}px</b> tall at row {Math.round(pendingCalibClicks[0].y)}
                        </p>
                        <Field label="Real height (feet)">
                          <TextInput value={pendingRealHeightFeet} onChange={(e) => setPendingRealHeightFeet(e.target.value)} />
                        </Field>
                      </>
                    )}
                    <div className="flex gap-2">
                      <GhostButton onClick={() => setPendingCalibClicks([])}>Reset</GhostButton>
                      {pendingCalibClicks.length === 2 && <PrimaryButton onClick={addCalibrationRow}>Add</PrimaryButton>}
                    </div>
                  </div>
                )}
                <div className="max-h-36 overflow-y-auto rounded-lg border" style={{ borderColor: 'var(--line)' }}>
                  {calibrationPoints.length === 0 ? (
                    <p className="p-3 text-xs" style={{ color: 'var(--ink-faint)' }}>No calibration points yet.</p>
                  ) : (
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b" style={{ borderColor: 'var(--line)' }}>
                          <th className="px-2 py-1.5 text-left">Pixel Y</th>
                          <th className="px-2 py-1.5 text-left">Ref height (px)</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {calibrationPoints.map((cp, i) => (
                          <tr key={i} className="border-b last:border-0" style={{ borderColor: 'var(--line)' }}>
                            <td className="px-2 py-1.5">{cp.pixel_y}</td>
                            <td className="px-2 py-1.5">{cp.reference_height_px}</td>
                            <td className="px-2 py-1.5 text-right">
                              <button style={{ color: 'var(--bad)' }} onClick={() => setCalibrationPoints((prev) => prev.filter((_, idx) => idx !== i))}>
                                Remove
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Adult height ratio">
                    <TextInput value={adultRatio} onChange={(e) => setAdultRatio(e.target.value)} />
                  </Field>
                  <Field label="Child height ratio">
                    <TextInput value={childRatio} onChange={(e) => setChildRatio(e.target.value)} />
                  </Field>
                </div>
                <PrimaryButton disabled={saving} onClick={saveCalibration}>Save calibration</PrimaryButton>
              </>
            )}
            {message && <p className="text-xs" style={{ color: 'var(--ink-faint)' }}>{message}</p>}
          </div>
        </div>
      )}
    </Modal>
  );
}
