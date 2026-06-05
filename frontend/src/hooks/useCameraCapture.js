import { useEffect, useRef, useState } from "react";

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export default function useCameraCapture() {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [cameraError, setCameraError] = useState("");

  const ensureStream = async () => {
    if (streamRef.current) return streamRef.current;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 360 } },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraError("");
      return stream;
    } catch (e) {
      const message = e?.name === "NotAllowedError" ? "Camera permission denied." : "Unable to access camera.";
      setCameraError(message);
      throw new Error(message);
    }
  };

  const captureBlob = async () => {
    await ensureStream();
    const video = videoRef.current;
    if (!video) throw new Error("Camera video element not ready.");

    let tries = 0;
    while ((video.readyState < 2 || !video.videoWidth || !video.videoHeight) && tries < 20) {
      // Wait for stable frame availability
      // eslint-disable-next-line no-await-in-loop
      await wait(60);
      tries += 1;
    }
    if (video.readyState < 2 || !video.videoWidth || !video.videoHeight) {
      throw new Error("Camera stream not ready for capture.");
    }

    await wait(120);
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    return new Promise((resolve, reject) => {
      canvas.toBlob(
        (blob) => {
          if (!blob) reject(new Error("Failed to capture identity frame."));
          else resolve(blob);
        },
        "image/jpeg",
        0.9
      );
    });
  };

  const stop = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) videoRef.current.srcObject = null;
  };

  /** Returns false when verification camera is not usable (permission, ended track, etc.). */
  const checkCameraOperational = () => {
    const stream = streamRef.current;
    if (!stream) return false;
    const videoTrack = stream.getVideoTracks()[0];
    if (!videoTrack) return false;
    if (videoTrack.readyState !== "live") return false;
    if (!videoTrack.enabled) return false;
    if (videoTrack.muted) return false;
    return true;
  };

  useEffect(() => stop, []);

  return { videoRef, cameraError, ensureStream, captureBlob, stop, checkCameraOperational };
}
