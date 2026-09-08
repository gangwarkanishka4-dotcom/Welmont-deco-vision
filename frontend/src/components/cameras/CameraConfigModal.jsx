import { useEffect, useRef, useState } from 'react';
import { Modal } from '../Modal.jsx';
import { Spinner } from '../Spinner.jsx';
import { api } from '../../services/api.js';

// Must match backend Settings.reference_adult_height_cm — the assumed
// average adult height that a calibration reference_height_px represents.
// Letting the user measure ANY known-height person/object (not necessarily
// an actual adult) and telling us its real height lets us scale their
// measured pixel height to what an "average adult" would measure at that
// same row, per the formula in addCalibrationRow below.
const REFERENCE_ADULT_HEIGHT_CM = 165;
const FEET_TO_CM = 30.48;

export function CameraConfigModal({ open, onClose, camera }) {
  const [mode, setMode] = useState('roi');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  const [roiPoints, setRoiPoints] = useState([]);
  const [calibrationPoints, setCalibrationPoints] = useState([]);
  const [adultRatio, setAdultRatio] = useState('1.0');
  const [childRatio, setChildRatio] = useState('0.56');
  // Two clicks measure one calibration point directly on the image instead
  // of requiring the user to type a pixel-height number they'd otherwise
  // have to work out by hand: click 1 = feet, click 2 = top of head.
  const [pendingCalibClicks, setPendingCalibClicks] = useState([]);
  const [pendingRealHeightFeet, setPendingRealHeightFeet] = useState('5.5');
  const [gateLine, setGateLine] = useState([]);
  const [gateInside, setGateInside] = useState(null);

  const containerRef = useRef(null);
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

  // Native (camera resolution) <-> display (rendered canvas pixels) scaling. The backend expects
  // ROI/calibration coordinates in the camera's own resolution_width/resolution_height space,
  // but clicks land in whatever size the canvas is actually rendered at in the browser.
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
      ctx.strokeStyle = '#4d9fff';
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.fillStyle = 'rgba(77,159,255,0.15)';
      if (pts.length > 2) ctx.fill();
      pts.forEach((p) => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
        ctx.fillStyle = '#4d9fff';
        ctx.fill();
      });
    }

    calibrationPoints.forEach((cp) => {
      const y = toDisplay({ x: 0, y: cp.pixel_y }).y;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(canvas.width, y);
      ctx.strokeStyle = '#f59e0b';
      ctx.lineWidth = 1;
      ctx.setLineDash([6, 4]);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = '#f59e0b';
      ctx.font = '11px sans-serif';
      ctx.fillText(`${cp.reference_height_px}px ref`, 6, y - 4);
    });

    if (pendingCalibClicks.length > 0) {
      const pts = pendingCalibClicks.map(toDisplay);
      pts.forEach((p, i) => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
        ctx.fillStyle = '#22c55e';
        ctx.fill();
        ctx.font = '11px sans-serif';
        ctx.fillStyle = '#22c55e';
        ctx.fillText(i === 0 ? 'feet' : 'head', p.x + 8, p.y + 4);
      });
      if (pts.length === 2) {
        ctx.beginPath();
        ctx.moveTo(pts[0].x, pts[0].y);
        ctx.lineTo(pts[1].x, pts[1].y);
        ctx.strokeStyle = '#22c55e';
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
        ctx.strokeStyle = '#ef4444';
        ctx.lineWidth = 3;
        ctx.stroke();
      }
      pts.forEach((p) => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
        ctx.fillStyle = '#ef4444';
        ctx.fill();
      });
    }
    if (gateInside) {
      const p = toDisplay(gateInside);
      ctx.beginPath();
      ctx.arc(p.x, p.y, 6, 0, Math.PI * 2);
      ctx.fillStyle = '#22c55e';
      ctx.fill();
      ctx.font = '11px sans-serif';
      ctx.fillStyle = '#22c55e';
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
    // Scale to what an average adult (REFERENCE_ADULT_HEIGHT_CM) would
    // measure at this same row, since that's what reference_height_px means
    // to the backend — the person/object actually measured doesn't need to
    // be that height itself.
    const referenceHeightPx = Math.round(measuredPx * (REFERENCE_ADULT_HEIGHT_CM / realHeightCm));
    setCalibrationPoints((prev) => [...prev, { pixel_y: Math.round(feetPoint.y), reference_height_px: referenceHeightPx }]);
    setPendingCalibClicks([]);
  };

  return (
    <Modal open={open} onClose={onClose} title={`Configure — ${camera.name}`} widthClassName="max-w-4xl">
      <div className="mb-3 flex gap-2">
        <button className={mode === 'roi' ? 'btn-primary' : 'btn-secondary'} onClick={() => setMode('roi')}>
          Region of Interest
        </button>
        <button className={mode === 'calibration' ? 'btn-primary' : 'btn-secondary'} onClick={() => setMode('calibration')}>
          Height Calibration
        </button>
        <button className={mode === 'gate' ? 'btn-primary' : 'btn-secondary'} onClick={() => setMode('gate')}>
          Gate Line
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-10">
          <Spinner className="h-6 w-6 text-accent-400" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
          <div
            ref={containerRef}
            className="relative overflow-hidden rounded-md bg-black"
            style={{ aspectRatio: `${camera.resolution_width} / ${camera.resolution_height}` }}
          >
            <img src={api.streamUrl(camera.id)} alt={camera.name} className="absolute inset-0 h-full w-full object-contain" />
            <canvas ref={canvasRef} className="absolute inset-0 h-full w-full cursor-crosshair" onClick={onCanvasClick} />
          </div>

          <div className="flex flex-col gap-3">
            {mode === 'roi' ? (
              <>
                <p className="text-xs text-slate-400">
                  Click on the image to add polygon points ({roiPoints.length} point{roiPoints.length === 1 ? '' : 's'}).
                  Coordinates are scaled to the camera's native {camera.resolution_width}×{camera.resolution_height} resolution.
                </p>
                <div className="flex gap-2">
                  <button className="btn-secondary flex-1" onClick={() => setRoiPoints([])}>
                    Reset
                  </button>
                  <button className="btn-primary flex-1" disabled={saving} onClick={saveRoi}>
                    {saving ? <Spinner /> : 'Save ROI'}
                  </button>
                </div>
              </>
            ) : mode === 'gate' ? (
              <>
                <p className="text-xs text-slate-400">
                  Click 2 points to draw the gate/entrance line, then a 3rd point anywhere clearly inside the classroom
                  (green) to mark which side is "inside." A tracked person is only counted as entering when they cross
                  this line from outside to inside — merely standing near the gate doesn't count.
                </p>
                <p className="text-xs text-slate-500">
                  Line points: {gateLine.length}/2 {gateInside ? '· inside point set' : ''}
                </p>
                <div className="flex gap-2">
                  <button
                    className="btn-secondary flex-1"
                    onClick={() => {
                      setGateLine([]);
                      setGateInside(null);
                    }}
                  >
                    Reset
                  </button>
                  <button className="btn-primary flex-1" disabled={saving || gateLine.length !== 2 || !gateInside} onClick={saveGate}>
                    {saving ? <Spinner /> : 'Save Gate Line'}
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="text-xs text-slate-400">
                  Stand any person or object of a known height where you want to calibrate. Click their feet, then
                  click the top of their head — the pixel height in between is measured automatically. Tell it the
                  real height of whoever/whatever you measured (in feet — doesn't have to be an adult), and it works
                  out the equivalent for this row. Add a few of these at different rows (near and far from the camera)
                  for best accuracy.
                </p>
                {pendingCalibClicks.length > 0 && (
                  <div className="flex items-end gap-2 rounded-md border border-surface-600 p-2">
                    <div className="flex-1 text-xs text-slate-300">
                      {pendingCalibClicks.length === 1 ? (
                        <p>Feet marked at row {Math.round(pendingCalibClicks[0].y)}. Now click the top of their head.</p>
                      ) : (
                        <div className="flex items-end gap-2">
                          <p>
                            Measured: <span className="font-semibold text-slate-100">
                              {Math.round(Math.abs(pendingCalibClicks[1].y - pendingCalibClicks[0].y))}px
                            </span>{' '}
                            tall at row {Math.round(pendingCalibClicks[0].y)}
                          </p>
                          <div>
                            <label className="label">Real height (feet)</label>
                            <input
                              className="input w-24"
                              value={pendingRealHeightFeet}
                              onChange={(e) => setPendingRealHeightFeet(e.target.value)}
                            />
                          </div>
                        </div>
                      )}
                    </div>
                    <button className="btn-secondary" onClick={() => setPendingCalibClicks([])}>
                      Reset
                    </button>
                    {pendingCalibClicks.length === 2 && (
                      <button className="btn-primary" onClick={addCalibrationRow}>
                        Add
                      </button>
                    )}
                  </div>
                )}
                <div className="max-h-40 overflow-y-auto rounded-md border border-surface-700">
                  {calibrationPoints.length === 0 ? (
                    <p className="p-3 text-xs text-slate-500">No calibration points yet.</p>
                  ) : (
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-surface-700 text-slate-500">
                          <th className="px-2 py-1.5 text-left">Pixel Y</th>
                          <th className="px-2 py-1.5 text-left">Ref Height (px)</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {calibrationPoints.map((cp, i) => (
                          <tr key={i} className="border-b border-surface-800 last:border-0">
                            <td className="px-2 py-1.5 text-slate-300">{cp.pixel_y}</td>
                            <td className="px-2 py-1.5 text-slate-300">{cp.reference_height_px}</td>
                            <td className="px-2 py-1.5 text-right">
                              <button
                                className="text-red-400 hover:underline"
                                onClick={() => setCalibrationPoints((prev) => prev.filter((_, idx) => idx !== i))}
                              >
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
                  <div>
                    <label className="label">Adult Height Ratio</label>
                    <input className="input w-full" value={adultRatio} onChange={(e) => setAdultRatio(e.target.value)} />
                  </div>
                  <div>
                    <label className="label">Child Height Ratio</label>
                    <input className="input w-full" value={childRatio} onChange={(e) => setChildRatio(e.target.value)} />
                  </div>
                </div>
                <button className="btn-primary" disabled={saving} onClick={saveCalibration}>
                  {saving ? <Spinner /> : 'Save Calibration'}
                </button>
              </>
            )}
            {message && <p className="text-xs text-slate-400">{message}</p>}
          </div>
        </div>
      )}
    </Modal>
  );
}
