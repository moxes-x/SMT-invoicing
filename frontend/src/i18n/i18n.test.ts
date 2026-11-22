import { bem } from "./bem";
import { en, type Key } from "./en";
import { translate } from "./index";
import { ny } from "./ny";

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("translations", () => {
  it.each([
    ["bem", bem],
    ["ny", ny],
  ])("%s covers every key with the same placeholders", (_, dict) => {
    for (const key of Object.keys(en) as Key[]) {
      expect(dict[key], key).toBeTruthy();
      expect(placeholders(dict[key]!), key).toEqual(placeholders(en[key]));
    }
  });

  it("fills placeholders and falls back to English", () => {
    expect(translate("ny", "more.signedInAs", { email: "a@b.zm" })).toBe("Mwalowa ngati a@b.zm");
    expect(translate("en", "nav.home")).toBe("Home");
  });
});
