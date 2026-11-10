# Normalize and validate the declaration before any firmware outputs are replaced.
def require($ok; $why): if $ok then . else error($why) end;
def charset($allowed): type == "string" and (explode|all(. as $c | $allowed|index($c)));
def digits: [range(48;58)];
def letters: [range(65;91),range(97;123)];
def hexchars: digits + [range(97;103)];
def default($key; $value): if has($key) then . else .[$key] = $value end;
def object_keys($allowed; $required):
  require(type == "object"; "expected object") |
  require(((keys - $allowed)|length) == 0 and (($required - keys)|length) == 0; "unknown or missing declaration keys");
def text:
  require(type == "string"; "expected text") |
  require(length > 0 and length <= 256 and (explode|all(. >= 32)); "invalid text");
def ident: require(type == "string" and length>0 and length<=63 and (.[0:1]|charset(letters)) and charset(letters+digits+[45,95]); "invalid FIT identifier");
def relative:
  require(type == "string"; "expected relative path") |
  require(length>0 and charset(letters+digits+[95,46,47,45]) and (startswith("/")|not) and
    (split("/")|all(length > 0 and . != "." and . != "..")); "noncanonical relative path");
def unsigned($bits):
  (if type == "string" and startswith("0x") and length>2 and (.[2:]|ascii_downcase|charset(hexchars)) then
    ascii_downcase | .[2:] | explode | reduce .[] as $c (0; . * 16 + (if $c < 58 then $c - 48 else $c - 87 end))
   else . end) |
  require(type == "number" and floor == . and . >= 0 and
    (if $bits == 32 then . < 4294967296 else . <= 9007199254740991 end); "invalid or inexact unsigned integer");
def positive: unsigned(64) | require(. > 0; "max_size must be positive");
def optional($key; f): if has($key) then .[$key] |= f else . end;

object_keys(["schema_version","description","version","rollback_index","hwids","architecture","components","release","factory","validation"];
  ["schema_version","description","version","hwids","architecture","components","release"]) |
require(.schema_version == 1 and (.schema_version|type) == "number"; "unsupported schema_version") |
.description |= text | .architecture |= ident |
if (.version|type) == "object" then
  .version |= object_keys(["file"];["file"]) |
  require((.version.file|type) == "string" and (.version.file|length)>0 and (.version.file|charset(letters+digits+[95,46,47,45])) and
    (.version.file|startswith("/")|not) and (.version.file|split("/")|all(length>0 and . != ".")); "invalid version file") |
  .version = $version
else . end |
require((.version|type) == "string" and (.version|split(".")|length)==3 and
  (.version|split(".")|all(length>0 and charset(digits) and (. == "0" or .[0:1] != "0"))); "version must be major.minor.patch") |
(.version|split(".")|map(tonumber)) as $v |
require($v[0] <= 65535 and $v[1] <= 255 and $v[2] <= 255 and ($v|add)>0; "version out of range") |
default("rollback_index";0) | .rollback_index |= unsigned(32) |
require((.hwids|type) == "array" and (.hwids|length)>0 and (.hwids|length)<=256; "HWID allowlist required") |
require((.hwids|all(type == "string" and length==16 and charset(hexchars) and .[0:1]=="1" and .[13:]=="000" and .[1:3] != "00" and .[3:7] != "0000" and .[7:11] != "0000")) and
  (.hwids|unique|length) == (.hwids|length); "invalid or duplicate HWID") |
. as $board |
.components |= (object_keys(["bootloader","kernel","rootfs"];["bootloader","kernel","rootfs"]) |
  with_entries(.key as $name | .value |= (
    (if $name == "kernel" then ["kernel","fdt","ramdisk"] elif $name == "bootloader" then ["firmware","loadables"] else ["firmware"] end) as $roles |
    object_keys(["description","os","max_size","images","verity"] + $roles; ["images"]) |
    default("description";($board.description + " " + $name)) | .description |= text |
    optional("os"; ident) | optional("max_size"; positive) |
    require((has("verity")|not) or ($name == "rootfs" and (.verity|type) == "boolean"); "verity is a rootfs boolean") |
    require((.images|type) == "array" and (.images|length)>0 and (.images|length)<=16; "component images required") |
    . as $component |
    .images |= map(
      object_keys(["name","file","description","architecture","type","compression","os","load","entry","generate","max_size"];["name","file"]) |
      .name |= ident | .file |= relative |
      default("description";.name) | .description |= text |
      default("architecture";$board.architecture) | .architecture |= ident |
      default("type";"firmware") | default("compression";"none") |
      require(.type as $t | ["firmware","kernel","flat_dt","ramdisk"]|index($t); "unsupported image type") |
      require(.compression as $c | ["none","gzip","bzip2","lzma","lzo","lz4","zstd"]|index($c); "unsupported compression") |
      if .type == "flat_dt" then del(.os) elif has("os") or ($component|has("os")) then default("os";$component.os) | .os |= ident else . end |
      optional("load";unsigned(64)) | optional("entry";unsigned(64)) | optional("max_size";positive) |
      require((has("generate")|not) or (.generate == "initramfs" and $name == "kernel" and .type == "ramdisk"); "invalid generated image")) |
    require((.images|map(.name)|unique|length) == (.images|length); "duplicate image node") |
    .images as $images |
    reduce ($roles[]|select(. != "loadables")) as $role (. ;
      if has($role) then
        .[$role] |= ident |
        require(.[$role] as $node | $images|any(.name == $node and .type == ({firmware:"firmware",kernel:"kernel",fdt:"flat_dt",ramdisk:"ramdisk"}[$role])); "missing or wrong image reference")
      else . end) |
    require(has(if $name == "kernel" then "kernel" else "firmware" end); "component needs boot reference") |
    require($name != "kernel" or (.kernel as $k | $images|any(.name == $k and has("load") and has("entry"))); "kernel load and entry required") |
    require((has("loadables")|not) or (.loadables|type) == "array"; "loadables must be an array") |
    ([.[$roles[]]|select(type == "string")] + (.loadables // [])) as $references |
    require(($references|unique|length) == ($references|length) and ($references|sort) == ($images|map(.name)|sort); "each image must be referenced exactly once") |
    require($name != "rootfs" or ($images|length) == 1; "rootfs needs one image")))) |
require((.components.rootfs.verity|not) or
  (.components.kernel|has("fdt") and has("ramdisk")) and .components.rootfs.images[0].compression == "none"; "verity requires fdt, ramdisk and uncompressed rootfs") |
[.components[].images[].file] as $inputs |
[.components[].images[]|select(has("generate"))|.file] as $generated |
require(($generated|unique|length) == ($generated|length) and all($generated[]; . as $file | [$inputs[]|select(. == $file)]|length == 1); "generated image path collision") |
require(all($inputs[]; . as $file | (["firmware.json","firmware-identity.json","layout-validation.json","build-manifest.json","meta0.bin","meta1.bin"]|index($file)|not) and
  ([ ["bootloader","kernel","rootfs","release"][] as $c | ["its","itb"][] as $s | "release/"+$c+"."+$s ]|index($file)|not)); "input collides with output") |
.release |= (object_keys(["description","manifest","components"];["components"]) |
  default("description";($board.description + " release")) | .description |= text |
  default("manifest";$board.description) | .manifest |= text |
  require((.components|type) == "array" and (.components|length)>0 and
    (.components|unique|length) == (.components|length) and (["kernel","rootfs"] - .components|length) == 0 and
    (.components - ["bootloader","kernel","rootfs"]|length) == 0; "invalid release components")) |
optional("factory"; object_keys(["layout","environment"];["layout"]) | map_values(relative)) |
optional("validation"; object_keys(["linux_layout","uboot_dtbs"];["linux_layout","uboot_dtbs"]) |
  .linux_layout |= relative |
  require((.uboot_dtbs|type) == "array" and (.uboot_dtbs|length)>0 and (.uboot_dtbs|length)<=8 and
    (.uboot_dtbs|unique|length) == (.uboot_dtbs|length); "invalid U-Boot DTB list") |
  .uboot_dtbs |= map(relative)) |
require((has("validation")|not) or (.factory|has("environment")); "layout validation requires factory environment")
