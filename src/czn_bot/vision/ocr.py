"""
Centralized OCR Service & Hybrid Verification Engine for Chaos Zero Nightmare Bot.

Technology:
- Primary: Windows Native OCR (Windows.Media.Ocr.OcrEngine via WinRT)
  Delivers ultra-fast recognition (~1.5ms to ~15ms) without heavy AI model weights.
- Fallback: RapidOCR (if installed) or graceful empty fallback.

API:
- read_text(image_or_crop) -> str: Extract all text from an image region.
- find_text(screen, text_query, region=None) -> Optional[Tuple[int, int]]:
    Find center coordinates (cx, cy) of a target word/phrase.
- verify_button_text(screen, box_or_point, expected_words, expand_pad=25) -> bool:
    Two-stage hybrid verification of button labels with automatic padding expansion.
"""

import asyncio
import concurrent.futures
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
import cv2
import numpy as np

logger = logging.getLogger("ChaosBot.OCR")

# Lazy-loaded backend handles
_WINRT_AVAILABLE: Optional[bool] = None
_RAPIDOCR_ENGINE: Any = None


def _check_winrt_available() -> bool:
    global _WINRT_AVAILABLE
    if _WINRT_AVAILABLE is None:
        try:
            import winrt.windows.media.ocr as _ocr  # noqa: F401
            import winrt.windows.graphics.imaging as _imaging  # noqa: F401
            import winrt.windows.storage.streams as _streams  # noqa: F401
            import winrt.windows.foundation.collections as _col  # noqa: F401
            _WINRT_AVAILABLE = True
            logger.info("Windows Native OCR (WinRT) backend loaded successfully.")
        except Exception as e:
            logger.warning(f"Windows Native OCR (WinRT) unavailable: {e}")
            _WINRT_AVAILABLE = False
    return _WINRT_AVAILABLE


def _get_rapidocr_engine() -> Any:
    global _RAPIDOCR_ENGINE
    if _RAPIDOCR_ENGINE is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _RAPIDOCR_ENGINE = RapidOCR()
            logger.info("RapidOCR fallback backend loaded successfully.")
        except Exception:
            _RAPIDOCR_ENGINE = False
    return _RAPIDOCR_ENGINE if _RAPIDOCR_ENGINE is not False else None


class OcrService:
    """
    Shared OCR Service providing fast text extraction and hybrid button verification.
    """

    def __init__(self, preferred_language: str = "en-US"):
        self.preferred_language = preferred_language
        self._engine = None
        self._init_backend()

    def _init_backend(self) -> None:
        """Initialize the primary Windows Media OCR engine if supported."""
        if _check_winrt_available():
            try:
                import winrt.windows.media.ocr as ocr
                import winrt.windows.globalization as glob

                try:
                    lang = glob.Language(self.preferred_language)
                    if ocr.OcrEngine.is_language_supported(lang):
                        self._engine = ocr.OcrEngine.try_create_from_language(lang)
                except Exception:
                    self._engine = None

                if self._engine is None:
                    self._engine = ocr.OcrEngine.try_create_from_user_profile_languages()

                if self._engine:
                    tag = getattr(self._engine.recognizer_language, "language_tag", "unknown")
                    logger.debug(f"OcrService initialized with Windows Native OCR [{tag}].")
            except Exception as e:
                logger.warning(f"Could not instantiate Windows OcrEngine: {e}")
                self._engine = None

    @property
    def is_available(self) -> bool:
        """Check if any OCR backend (Windows Native OCR or RapidOCR) is available."""
        return self._engine is not None or _get_rapidocr_engine() is not None

    # ── Internal Async / Sync Bridge ─────────────────────────
    @staticmethod
    def _run_coroutine_sync(coro):
        """
        Safely execute an async coroutine synchronously, even when inside
        an existing event loop or background thread.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        else:
            return asyncio.run(coro)

    # ── Image Preprocessing ──────────────────────────────────
    @staticmethod
    def preprocess_image(image: np.ndarray, upscale_small: bool = True) -> np.ndarray:
        """
        Preprocess image crop for optimal OCR accuracy:
        - Ensures minimum dimensions of 60x60 (Windows OCR requires >= 40x40).
        - Upscale small ROIs (height < 45 or width < 120) by 2x or more.
        - Preserves aspect ratio.
        """
        if image is None or image.size == 0:
            return image

        proc = image
        h, w = proc.shape[:2]
        if h <= 0 or w <= 0:
            return image

        if upscale_small:
            min_dim = 60
            scale = 1.0
            if h < min_dim or w < min_dim:
                scale = max(min_dim / float(max(1, h)), min_dim / float(max(1, w)), scale)
            if h < 45 or w < 120:
                scale = max(scale, 2.0)
            if scale > 1.0:
                new_w = max(min_dim, int(round(w * scale)))
                new_h = max(min_dim, int(round(h * scale)))
                proc = cv2.resize(proc, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

        return proc

    # ── Low-level Recognition ────────────────────────────────
    def recognize_elements(
        self, image: np.ndarray, preprocess: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Recognize text elements with bounding boxes and normalized text.
        Returns a list of dicts:
        [
            {
                "text": "CONFIRM",
                "rect": (x, y, w, h),
                "center": (cx, cy)
            },
            ...
        ]
        Coordinates are relative to the input image.
        """
        if image is None or image.size == 0:
            return []

        orig_h, orig_w = image.shape[:2]
        if orig_h < 5 or orig_w < 5:
            return []
        proc = self.preprocess_image(image, upscale_small=True) if preprocess else image
        proc_h, proc_w = proc.shape[:2]

        scale_x = orig_w / float(proc_w) if proc_w > 0 else 1.0
        scale_y = orig_h / float(proc_h) if proc_h > 0 else 1.0

        elements: List[Dict[str, Any]] = []

        # 1. Primary backend: Windows Native OCR
        if self._engine is not None:
            try:
                import winrt.windows.graphics.imaging as imaging
                import winrt.windows.storage.streams as streams

                # Convert to BGRA
                if len(proc.shape) == 2:
                    bgra = cv2.cvtColor(proc, cv2.COLOR_GRAY2BGRA)
                elif proc.shape[2] == 3:
                    bgra = cv2.cvtColor(proc, cv2.COLOR_BGR2BGRA)
                else:
                    bgra = proc

                writer = streams.DataWriter()
                writer.write_bytes(bgra.tobytes())
                ibuffer = writer.detach_buffer()

                sb = imaging.SoftwareBitmap(
                    imaging.BitmapPixelFormat.BGRA8,
                    proc_w,
                    proc_h,
                    imaging.BitmapAlphaMode.PREMULTIPLIED,
                )
                sb.copy_from_buffer(ibuffer)

                async def _rec():
                    return await self._engine.recognize_async(sb)

                result = self._run_coroutine_sync(_rec())

                for line in result.lines:
                    for word in line.words:
                        r = word.bounding_rect
                        # Map back to original coordinate space
                        orig_rx = int(round(r.x * scale_x))
                        orig_ry = int(round(r.y * scale_y))
                        orig_rw = int(round(r.width * scale_x))
                        orig_rh = int(round(r.height * scale_y))
                        cx = orig_rx + orig_rw // 2
                        cy = orig_ry + orig_rh // 2
                        elements.append({
                            "text": str(word.text).strip(),
                            "rect": (orig_rx, orig_ry, orig_rw, orig_rh),
                            "center": (cx, cy),
                        })

                # Always return Windows OCR result when engine succeeded
                return elements

            except Exception as e:
                logger.debug(f"Windows OCR recognize_elements error: {e}")

        # 2. Fallback backend: RapidOCR (only if Windows OCR was unavailable or errored)
        rapid = _get_rapidocr_engine()
        if rapid is not None:
            try:
                res, _ = rapid(proc)
                if res:
                    for item in res:
                        box, text, _ = item
                        xs = [pt[0] for pt in box]
                        ys = [pt[1] for pt in box]
                        rx = int(round(min(xs) * scale_x))
                        ry = int(round(min(ys) * scale_y))
                        rw = int(round((max(xs) - min(xs)) * scale_x))
                        rh = int(round((max(ys) - min(ys)) * scale_y))
                        elements.append({
                            "text": str(text).strip(),
                            "rect": (rx, ry, rw, rh),
                            "center": (rx + rw // 2, ry + rh // 2),
                        })
                    return elements
            except Exception as e_rap:
                logger.debug(f"RapidOCR recognize_elements error: {e_rap}")

        return elements

    # ── High-level API ───────────────────────────────────────
    def read_text(self, image_or_crop: np.ndarray, preprocess: bool = True) -> str:
        """
        Recognize and return all plain text from the given image or crop.
        """
        if image_or_crop is None or image_or_crop.size == 0:
            return ""

        elements = self.recognize_elements(image_or_crop, preprocess=preprocess)
        if not elements:
            return ""

        return " ".join(e["text"] for e in elements if e.get("text")).strip()

    def find_text(
        self,
        screen: np.ndarray,
        text_query: str,
        region: Optional[Tuple[int, int, int, int]] = None,
        preprocess: bool = True,
    ) -> Optional[Tuple[int, int]]:
        """
        Locate the center coordinates (center_x, center_y) of a keyword on screen.

        Args:
            screen: Full screen (or large image) in BGR format.
            text_query: Keyword to search for (case-insensitive substring).
            region: Optional (rx, ry, rw, rh) bounding box to restrict the search.
            preprocess: Whether to apply upscaling/contrast enhancement.

        Returns:
            (center_x, center_y) in full screen coordinates, or None if not found.
        """
        if screen is None or screen.size == 0 or not text_query:
            return None

        ox, oy = 0, 0
        crop = screen
        if region is not None:
            rx, ry, rw, rh = region
            h, w = screen.shape[:2]
            rx = max(0, min(rx, w - 1))
            ry = max(0, min(ry, h - 1))
            rw = max(1, min(rw, w - rx))
            rh = max(1, min(rh, h - ry))
            crop = screen[ry:ry + rh, rx:rx + rw]
            ox, oy = rx, ry

        elements = self.recognize_elements(crop, preprocess=preprocess)
        query_lower = text_query.strip().lower()

        # 1. Exact or substring match in individual words
        for elem in elements:
            word_lower = elem["text"].lower()
            if query_lower in word_lower:
                local_cx, local_cy = elem["center"]
                return (ox + local_cx, oy + local_cy)

        # 2. Check full joined line if query contains spaces
        if " " in query_lower:
            full_text = " ".join(e["text"] for e in elements).lower()
            if query_lower in full_text:
                # Find matching elements span
                matching_elems = [e for e in elements if any(w in query_lower for w in e["text"].lower().split())]
                if matching_elems:
                    avg_cx = int(sum(e["center"][0] for e in matching_elems) / len(matching_elems))
                    avg_cy = int(sum(e["center"][1] for e in matching_elems) / len(matching_elems))
                    return (ox + avg_cx, oy + avg_cy)

        return None

    def verify_button_text(
        self,
        screen: np.ndarray,
        box_or_point: Union[Tuple[int, int], Tuple[int, int, int, int]],
        expected_words: Union[str, List[str]],
        expand_pad: int = 25,
    ) -> bool:
        """
        Two-stage Hybrid Verification for critical buttons:
        Stage 1: Verify OCR text in the initial crop.
        Stage 2: If unverified, expand crop area by expand_pad (default 25px) and re-verify.

        Args:
            screen: Full screen (1600x900) BGR image.
            box_or_point: Either (center_x, center_y) or (x, y, w, h).
            expected_words: String or list of acceptable strings (e.g. 'Confirm' or ['confirm', 'xác nhận']).
            expand_pad: Pixel padding to add if initial crop check misses.

        Returns:
            True if any expected keyword is confirmed, False otherwise.
        """
        if screen is None or screen.size == 0:
            return False

        if isinstance(expected_words, str):
            expected_list = [expected_words.lower()]
        else:
            expected_list = [w.lower() for w in expected_words]

        h, w = screen.shape[:2]

        # Determine initial bounding box
        if len(box_or_point) == 2:
            cx, cy = box_or_point
            bw, bh = 180, 70
            bx = max(0, cx - bw // 2)
            by = max(0, cy - bh // 2)
        elif len(box_or_point) == 4:
            bx, by, bw, bh = box_or_point
        else:
            return False

        def _matches(crop_img: np.ndarray) -> bool:
            text = self.read_text(crop_img, preprocess=True).lower()
            if not text:
                return False
            for target in expected_list:
                if target in text:
                    return True
            return False

        # Stage 1: Check initial region
        bx = max(0, min(bx, w - 1))
        by = max(0, min(by, h - 1))
        bw = max(1, min(bw, w - bx))
        bh = max(1, min(bh, h - by))
        crop1 = screen[by:by + bh, bx:bx + bw]

        if _matches(crop1):
            logger.debug(f"[HybridVerification] Stage 1 MATCH for {expected_list} at ({bx}, {by}, {bw}, {bh})")
            return True

        # Stage 2: Expand crop area by expand_pad (25px)
        if expand_pad > 0:
            exp_x = max(0, bx - expand_pad)
            exp_y = max(0, by - expand_pad)
            exp_w = min(w - exp_x, bw + 2 * expand_pad)
            exp_h = min(h - exp_y, bh + 2 * expand_pad)
            crop2 = screen[exp_y:exp_y + exp_h, exp_x:exp_x + exp_w]

            if _matches(crop2):
                logger.debug(
                    f"[HybridVerification] Stage 2 (+{expand_pad}px expanded) MATCH for "
                    f"{expected_list} at ({exp_x}, {exp_y}, {exp_w}, {exp_h})"
                )
                return True

        logger.debug(f"[HybridVerification] REJECTED {expected_list} at {box_or_point}")
        return False


# Global default service instance
_DEFAULT_OCR_SERVICE: Optional[OcrService] = None


def get_ocr_service() -> OcrService:
    """Retrieve or lazily initialize the singleton OcrService instance."""
    global _DEFAULT_OCR_SERVICE
    if _DEFAULT_OCR_SERVICE is None:
        _DEFAULT_OCR_SERVICE = OcrService()
    return _DEFAULT_OCR_SERVICE


def read_text(image_or_crop: np.ndarray, preprocess: bool = True) -> str:
    """Top-level convenience function for read_text."""
    return get_ocr_service().read_text(image_or_crop, preprocess=preprocess)


def find_text(
    screen: np.ndarray,
    text_query: str,
    region: Optional[Tuple[int, int, int, int]] = None,
    preprocess: bool = True,
) -> Optional[Tuple[int, int]]:
    """Top-level convenience function for find_text."""
    return get_ocr_service().find_text(screen, text_query, region=region, preprocess=preprocess)


def verify_button_text(
    screen: np.ndarray,
    box_or_point: Union[Tuple[int, int], Tuple[int, int, int, int]],
    expected_words: Union[str, List[str]],
    expand_pad: int = 25,
) -> bool:
    """Top-level convenience function for verify_button_text."""
    return get_ocr_service().verify_button_text(
        screen, box_or_point, expected_words, expand_pad=expand_pad
    )


def is_ocr_available() -> bool:
    """Top-level check if OCR backend is available."""
    return get_ocr_service().is_available
