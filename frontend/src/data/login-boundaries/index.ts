import { decodeBoundaries } from './codec'
import { statesChunk1 } from './states-1'
import { statesChunk2 } from './states-2'
import { statesChunk3 } from './states-3'
import { statesChunk4 } from './states-4'
import { statesChunk5 } from './states-5'
import { statesChunk6 } from './states-6'
import { districtsChunk1 } from './districts-1'
import { districtsChunk2 } from './districts-2'
import { districtsChunk3 } from './districts-3'
import { districtsChunk4 } from './districts-4'
import { districtsChunk5 } from './districts-5'
import { districtsChunk6 } from './districts-6'

export const indiaStateFeatures = decodeBoundaries([
  ...statesChunk1,
  ...statesChunk2,
  ...statesChunk3,
  ...statesChunk4,
  ...statesChunk5,
  ...statesChunk6,
])

export const karnatakaDistrictFeatures = decodeBoundaries([
  ...districtsChunk1,
  ...districtsChunk2,
  ...districtsChunk3,
  ...districtsChunk4,
  ...districtsChunk5,
  ...districtsChunk6,
])
