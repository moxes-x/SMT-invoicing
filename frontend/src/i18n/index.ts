import { useMutation, useQueryClient } from "@tanstack/react-query";

import { meKey, useMe } from "@/api/auth";
import { api, type Me } from "@/api/client";

import { bem } from "./bem";
import { en, type Key } from "./en";
import { ny } from "./ny";

export type Lang = "en" | "bem" | "ny";
export type { Key };

const DICTS: Record<Lang, Partial<Record<Key, string>>> = { en, bem, ny };

export const LANGUAGES: { value: Lang; label: string }[] = [
  { value: "en", label: "English" },
  { value: "bem", label: "Icibemba" },
  { value: "ny", label: "Chinyanja" },
];

/** `{name}` placeholders, English when a word is missing. */
export function translate(lang: Lang, key: Key, vars?: Record<string, string | number>): string {
  let text = DICTS[lang]?.[key] ?? en[key];
  if (vars) for (const [k, v] of Object.entries(vars)) text = text.replaceAll(`{${k}}`, String(v));
  return text;
}

export function useLang(): Lang {
  const { data: me } = useMe();
  const lang = me?.user.language;
  return lang === "bem" || lang === "ny" ? lang : "en";
}

/** The app's words in the language the user picked under More → Language. */
export function useT() {
  const lang = useLang();
  return (key: Key, vars?: Record<string, string | number>) => translate(lang, key, vars);
}

export function useSetLanguage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (language: Lang) => api<Me>("/auth/me/", { method: "PATCH", json: { language } }),
    onSuccess: (me) => qc.setQueryData(meKey, me),
  });
}
