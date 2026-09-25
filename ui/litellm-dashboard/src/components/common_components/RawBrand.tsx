import { cn } from "@/lib/cva.config";
import rawLockup from "../../../public/assets/logos/raw_lockup.png";
import rawLockupDark from "../../../public/assets/logos/raw_lockup_dark.png";

export default function RawBrand({ className }: { className?: string }) {
  return (
    <>
      <img src={rawLockup.src} alt="RAW by Rabbitt" className={cn("w-auto", className, "dark:hidden")} />
      <img src={rawLockupDark.src} alt="" aria-hidden className={cn("w-auto", className, "hidden dark:block")} />
    </>
  );
}
