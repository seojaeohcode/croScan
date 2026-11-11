import { Composition } from "remotion";
import { CroScan, TOTAL } from "./Video";
export const Root = () => <Composition id="CroScan" component={CroScan} durationInFrames={TOTAL} fps={30} width={1920} height={1080} />;
