"""Plate reading: EasyOCR on the full frame + Indian-plate regex filter.

No YOLO detector: every pretrained Indian-plate YOLO checkpoint we know of lives
behind Roboflow/Kaggle logins, which the spec said to skip.
Instead, OCR boxes are grouped into lines; contiguous runs of boxes in a line,
and pairs of stacked lines (two-row plates), are tried as plate candidates.
"""
import base64
import threading
import time

import cv2
import numpy as np

from plates import normalize_ocr

ALLOW = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
MAX_W = 1280          # downscale big frames: big speed win on CPU
MAX_RUN = 5           # max OCR boxes joined into one candidate


class PlateReader:
    def __init__(self):
        import easyocr
        try:
            import torch
            gpu = torch.cuda.is_available()
        except Exception:
            gpu = False
        self.gpu = gpu
        self.reader = easyocr.Reader(["en"], gpu=gpu, verbose=False)
        self.lock = threading.Lock()   # one inference at a time

    # ---------- helpers ----------
    @staticmethod
    def _box(pts):
        pts = np.array(pts)
        x0, y0 = pts.min(axis=0)
        x1, y1 = pts.max(axis=0)
        return float(x0), float(y0), float(x1), float(y1)

    @staticmethod
    def _group_lines(dets):
        """Cluster detections whose vertical extents overlap into lines, sorted top->bottom, left->right."""
        lines = []
        for d in sorted(dets, key=lambda d: (d["box"][1] + d["box"][3]) / 2):
            cy = (d["box"][1] + d["box"][3]) / 2
            for line in lines:
                ly0 = min(x["box"][1] for x in line)
                ly1 = max(x["box"][3] for x in line)
                if ly0 <= cy <= ly1:
                    line.append(d)
                    break
            else:
                lines.append([d])
        return [sorted(l, key=lambda d: d["box"][0]) for l in lines]

    @staticmethod
    def _runs(line):
        for i in range(len(line)):
            for j in range(i + 1, min(i + MAX_RUN, len(line)) + 1):
                yield line[i:j]

    @staticmethod
    def _union(group):
        xs0, ys0, xs1, ys1 = zip(*[d["box"] for d in group])
        return min(xs0), min(ys0), max(xs1), max(ys1)

    def _candidates(self, dets):
        lines = self._group_lines(dets)
        groups = []
        for line in lines:
            groups.extend(self._runs(line))
        # two-row plates: a run in line k directly above a run in line k+1
        for a, b in zip(lines, lines[1:]):
            for ra in self._runs(a):
                ua = self._union(ra)
                h = ua[3] - ua[1]
                for rb in self._runs(b):
                    ub = self._union(rb)
                    gap = ub[1] - ua[3]
                    overlap = min(ua[2], ub[2]) - max(ua[0], ub[0])
                    width = min(ua[2] - ua[0], ub[2] - ub[0])
                    if -0.3 * h <= gap <= 1.0 * h and overlap > 0.5 * width:
                        groups.append(ra + rb)
        for g in groups:
            raw = "".join(d["text"] for d in g)
            res = normalize_ocr(raw)
            if res:
                plate, fixes = res
                conf = float(np.mean([d["conf"] for d in g]))
                yield {"plate": plate, "raw": raw, "conf": conf,
                       "score": conf * (0.85 ** fixes), "fixes": fixes,
                       "box": self._union(g)}

    # ---------- main entry ----------
    def read(self, img_bgr):
        t0 = time.time()
        h, w = img_bgr.shape[:2]
        if w > MAX_W:
            s = MAX_W / w
            img_bgr = cv2.resize(img_bgr, (MAX_W, int(h * s)), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

        with self.lock:
            results = self.reader.readtext(gray, allowlist=ALLOW, paragraph=False)

        dets = [{"box": self._box(b), "text": t, "conf": float(c)} for b, t, c in results if t.strip()]
        best = max(self._candidates(dets), key=lambda c: c["score"], default=None)

        out = {"plate": None, "raw_text": " | ".join(d["text"] for d in dets),
               "confidence": 0.0, "crop_b64": None, "ms": 0}
        if best:
            x0, y0, x1, y1 = best["box"]
            pad = int(0.15 * (y1 - y0)) + 4
            H, W = img_bgr.shape[:2]
            crop = img_bgr[max(0, int(y0) - pad):min(H, int(y1) + pad),
                           max(0, int(x0) - pad):min(W, int(x1) + pad)]
            ok, buf = cv2.imencode(".jpg", crop)
            out.update(plate=best["plate"], raw_text=best["raw"],
                       confidence=round(best["score"], 3),
                       crop_b64=base64.b64encode(buf).decode() if ok else None)
        out["ms"] = int((time.time() - t0) * 1000)
        return out
