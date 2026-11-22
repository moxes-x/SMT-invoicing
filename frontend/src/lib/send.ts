import { ApiError } from "@/api/client";
import type { SendBody, SendResult } from "@/api/resources";

export type Send = (body: SendBody) => Promise<SendResult>;

/**
 * Open WhatsApp click-to-chat. The window is opened before the request so mobile browsers
 * treat it as a direct result of the tap and don't block it as a popup.
 */
export async function sendViaWhatsAppLink(send: Send): Promise<void> {
  const win = window.open("", "_blank");
  try {
    const { url } = await send({ channel: "whatsapp_link" });
    if (!url) throw new Error("No link returned");
    if (win) win.location.href = url;
    else window.location.href = url;
  } catch (err) {
    win?.close();
    throw err;
  }
}

export function errorText(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}
