# DTS sources consumed by Buildroot's native host-uboot-tools/mkimage.
def strings: map(tojson)|join(", ");
def cells($n): "<" + ($n|tostring) + ">";
def cells64($n): "<" + (($n/4294967296|floor)|tostring) + " " + (($n%4294967296)|tostring) + ">";
def number: .version|split(".")|map(tonumber)|.[0]*65536+.[1]*256+.[2];
def metadata($name):
  "fw,type = " + ($name|tojson) + ";\n" +
  "fw,hwids = " + (.hwids|strings) + ";\n" +
  "fw,version = " + cells(number) + ";\n" +
  "fw,rollback-index = " + cells(.rollback_index) + ";\n" +
  "fw,build-time-minutes = " + cells($minutes) + ";";
def container($description; $images; $properties; $address_cells):
  "/dts-v1/;\n/ {\n description = " + ($description|tojson) + ";\n #address-cells = <" + ($address_cells|tostring) + ">;\n" +
  " images {\n" + $images + "\n };\n configurations {\n default = \"conf-1\";\n conf-1 {\n" +
  " description = " + ($description|tojson) + ";\n" + $properties + "\n };\n };\n};\n";
if $component == "release" then
  $identity[0] as $id |
  "manifest {\n description = \"Firmware release manifest\";\n data = " + (.release.manifest|tojson) +
  ";\n type = \"firmware\";\n arch = " + (.architecture|tojson) + ";\n compression = \"none\";\n hash-1 { algo = \"sha256\"; };\n};" as $images |
  (metadata("release") + "\nfw,tag = " + ($id.tag|tojson) + ";\nfw,firmware-id = " + ($id.firmware_id|tojson) +
   ";\nfw,components = " + (.release.components|strings) + ";\n" +
   (if (.release.components|index("bootloader")) != null then "fw,allow-bootloader;\n" else "" end) +
   ([ ["kernel","rootfs"][] as $name |
      "fw," + $name + "-payload-bytes = " + cells64($id[$name+"_bytes"]) + ";\n" +
      "fw," + $name + "-payload-sha256 = " + ($id[$name+"_sha256"]|tojson) + ";" ]|join("\n")) + "\n" +
   ([.release.components[] as $name |
      "fw,"+$name+"-file = "+($name+".itb"|tojson)+";\n"+
      "fw,"+$name+"-sha256 = "+($sha[0][$name]|tojson)+";" ]|join("\n")) + "\nfirmware = \"manifest\";") as $properties |
  container(.release.description; $images; $properties; 1)
else
  . as $board | .components[$component] as $settings |
  (if any($settings.images[]; (.load // 0)>4294967295 or (.entry // 0)>4294967295) then 2 else 1 end) as $count |
  ([$settings.images[] |
    . as $image |
    .name + " {\n description = " + (.description|tojson) + ";\n" +
    " data = /incbin/(" + ($files[0][$component][.name]|tojson) + ");\n" +
    " type = " + (.type|tojson) + ";\n arch = " + (.architecture|tojson) + ";\n compression = " + (.compression|tojson) + ";\n" +
    (if has("os") then "os = " + (.os|tojson) + ";\n" else "" end) +
    ([ ["load","entry"][] as $key | select($image|has($key)) |
      $key + " = " + (if $count==2 then cells64($image[$key]) else cells($image[$key]) end) + ";" ]|join("\n")) +
    "\n hash-1 { algo = \"sha256\"; };\n};"]|join("\n")) as $images |
  ($board|metadata($component)) + "\n" +
  ([ ["firmware","kernel","fdt","ramdisk"][] as $key | select($settings|has($key)) |
     $key+" = "+($settings[$key]|tojson)+";" ]|join("\n")) + "\n" +
  (if ($settings.loadables // []|length)>0 then "loadables = "+($settings.loadables|strings)+";" else "" end) as $properties |
  container($settings.description; $images; $properties; $count)
end
