import { useEffect, useRef, useState } from 'react';
import { Modal } from '../Modal.jsx';
import { Spinner } from '../Spinner.jsx';
import { api } from '../../services/api.js';

export function CameraConfigModal({ open, onClose, camera }) {
  const [mode, setMode] = useState('roi');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  const [roiPoints, setRoiPoints] = useState([]);
  const [calibrationPoints, setCalibrationPoints] = useState([]);
  const [adultRatio, setAdultRatio] = useState('1.0');
  const [childRatio, setChildRatio] = useState('0.6');
  const [pendingPixelY, setPendingPixelY] = useState(null);
  const [pendingHeight, setPendingHeight] = useState('');

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

    if (pendingPixelY !== null) {
      const y = toDisplay({ x: 0, y: pendingPixelY }).y;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(canvas.width, y);
      ctx.strokeStyle = '#22c55e';
      ctx.lineWidth = 1.5;
      ctx.stroke();
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
    } else {
      setPendingPixelY(Math.round(native.y));
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

  const addCalibrationRow = () => {
    if (pendingPixelY === null || !pendingHeight) return;
    setCalibrationPoints((prev) => [...prev, { pixel_y: pendingPixelY, reference_height_px: Number(pendingHeight) }]);
    setPendingPixelY(null);
    setPendingHeight('');
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
            ) : (
              <>
                <p className="text-xs text-slate-400">
                  Click a row/point on the image, enter the reference height for that pixel row, then add it. Adult/child
                  height ratios refine how the pipeline classifies a tracked box's height against the calibration curve.
                </p>
                {pendingPixelY !== null && (
                  <div className="flex items-end gap-2 rounded-md border border-surface-600 p-2">
                    <div className="flex-1">
                      <label className="label">Pixel Y: {pendingPixelY}</label>
                      <input
                        className="input w-full"
                        placeholder="Reference height (px)"
                        value={pendingHeight}
                        onChange={(e) => setPendingHeight(e.target.value)}
                      />
                    </div>
                    <button className="btn-primary" onClick={addCalibrationRow}>
                      Add
                    </button>
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
