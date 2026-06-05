import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";

/**
 * WebRTC camera preview + imperative capture as JPEG Blob.
 */
const CameraCapture = forwardRef(function CameraCapture({ onStatus }, ref) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [error, setError] = useState("");

  useImperativeHandle(ref, () => ({
    async captureBlob() {
      const video = videoRef.current;
      if (!video || !video.videoWidth) {
        throw new Error("Video not ready.");
      }
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0);
      return new Promise((resolve, reject) => {
        canvas.toBlob(
          (blob) => {
            if (!blob) reject(new Error("Capture failed."));
            else resolve(blob);
          },
          "image/jpeg",
          0.92
        );
      });
    },
  }));

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
        onStatus?.("Camera ready.");
      } catch (e) {
        setError(e?.message || "Camera access denied.");
        onStatus?.("Camera error.");
      }
    })();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, [onStatus]);

  return (
    <div className="space-y-3">
      <div className="overflow-hidden rounded-xl border border-slate-800 bg-black">
        <video ref={videoRef} autoPlay playsInline muted className="h-auto w-full max-h-[420px] object-cover" />
      </div>
      {error && <p className="text-sm text-red-400">{error}</p>}
    </div>
  );
});

export default CameraCapture;
