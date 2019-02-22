import torch
import torch.nn as nn
from model.blocks import DANetHead

class ESPNetDecoder():
    def __init__(self):

        # light-weight decoder
        self.level3_C = C(128 + 3, classes, 1, 1)
        self.br = nn.BatchNorm2d(classes, eps=1e-03)
        self.conv = CBR(19 + classes, classes, 3, 1)

        self.up_l3 = nn.Sequential(
            nn.ConvTranspose2d(classes, classes, 2, stride=2, padding=0, output_padding=0, bias=False))
        self.combine_l2_l3 = nn.Sequential(BR(2 * classes),
                                           DilatedParllelResidualBlockB(2 * classes, classes, add=False))

        self.up_l2 = nn.Sequential(
            nn.ConvTranspose2d(classes, classes, 2, stride=2, padding=0, output_padding=0, bias=False), BR(classes))

        self.classifier = nn.ConvTranspose2d(classes, classes, 2, stride=2, padding=0, output_padding=0, bias=False)

    def forward(self, input):
        '''
        :param input: RGB image
        :return: transformed feature map
        '''
        output0 = self.modules[0](input)
        inp1 = self.modules[1](input)
        inp2 = self.modules[2](input)

        output0_cat = self.modules[3](torch.cat([output0, inp1], 1))
        output1_0 = self.modules[4](output0_cat)  # down-sampled

        for i, layer in enumerate(self.modules[5]):
            if i == 0:
                output1 = layer(output1_0)
            else:
                output1 = layer(output1)

        output1_cat = self.modules[6](torch.cat([output1, output1_0, inp2], 1))

        output2_0 = self.modules[7](output1_cat)  # down-sampled
        for i, layer in enumerate(self.modules[8]):
            if i == 0:
                output2 = layer(output2_0)
            else:
                output2 = layer(output2)

        output2_cat = self.modules[9](torch.cat([output2_0, output2], 1))  # concatenate for feature map width expansion

        output2_c = self.up_l3(self.br(self.modules[10](output2_cat)))  # RUM

        output1_C = self.level3_C(output1_cat)  # project to C-dimensional space
        comb_l2_l3 = self.up_l2(self.combine_l2_l3(torch.cat([output1_C, output2_c], 1)))  # RUM

        concat_features = self.conv(torch.cat([comb_l2_l3, output0_cat], 1))

        classifier = self.classifier(concat_features)
        return classifier


class ENetDecoder():
    def __init__(self):
        # Stage 4 - Decoder
        self.upsample4_0 = UpsamplingBottleneck(
            128, 64, padding=1, dropout_prob=0.1, relu=decoder_relu)
        self.regular4_1 = RegularBottleneck(
            64, padding=1, dropout_prob=0.1, relu=decoder_relu)
        self.regular4_2 = RegularBottleneck(
            64, padding=1, dropout_prob=0.1, relu=decoder_relu)

        # Stage 5 - Decoder
        self.upsample5_0 = UpsamplingBottleneck(
            64, 16, padding=1, dropout_prob=0.1, relu=decoder_relu)
        self.regular5_1 = RegularBottleneck(
            16, padding=1, dropout_prob=0.1, relu=decoder_relu)
        self.transposed_conv = nn.ConvTranspose2d(
            16,
            num_classes,
            kernel_size=3,
            stride=2,
            padding=1,
            output_padding=1,
            bias=False)

    def forward(self, x):
        # Initial block
        x = self.initial_block(x)

        # Stage 1 - Encoder
        x, max_indices1_0 = self.downsample1_0(x)
        x = self.regular1_1(x)
        x = self.regular1_2(x)
        x = self.regular1_3(x)
        x = self.regular1_4(x)

        # Stage 2 - Encoder
        x, max_indices2_0 = self.downsample2_0(x)
        x = self.regular2_1(x)
        x = self.dilated2_2(x)
        x = self.asymmetric2_3(x)
        x = self.dilated2_4(x)
        x = self.regular2_5(x)
        x = self.dilated2_6(x)
        x = self.asymmetric2_7(x)
        x = self.dilated2_8(x)

        # Stage 3 - Encoder
        x = self.regular3_0(x)
        x = self.dilated3_1(x)
        x = self.asymmetric3_2(x)
        x = self.dilated3_3(x)
        x = self.regular3_4(x)
        x = self.dilated3_5(x)
        x = self.asymmetric3_6(x)
        x = self.dilated3_7(x)

        # Stage 4 - Decoder
        x = self.upsample4_0(x, max_indices2_0)
        x = self.regular4_1(x)
        x = self.regular4_2(x)

        # Stage 5 - Decoder
        x = self.upsample5_0(x, max_indices1_0)
        x = self.regular5_1(x)
        x = self.transposed_conv(x)

        return x


class FCNDecoder(nn.Module):
    def __init__(self, decode_layers, decode_channels, decode_last_stride, cout=64):
        super(FCNDecoder, self).__init__()
        self._in_channels = decode_channels
        self._out_channel = 64
        self._decode_layers = decode_layers
        self.score_net = nn.Sequential()
        self.deconv_net = nn.Sequential()
        self.bn_net = nn.Sequential()
        self.head = DANetHead(cout * 8, cout * 8, nn.BatchNorm2d)
        self.prehead = nn.Sequential(nn.Conv2d(cout, cout * 8, 1, bias=False), nn.BatchNorm2d(cout * 8), nn.ReLU())
        for i, cin in enumerate(self._in_channels):
            self.score_net.add_module("conv" + str(i + 1), self._conv_stage(cin, cout))
            if i > 0:
                self.deconv_net.add_module("deconv" + str(i), self._deconv_stage(cout))
        k_size = 2 * decode_last_stride
        padding = decode_last_stride // 2
        self.deconv_last = nn.ConvTranspose2d(cout * 8, cout, k_size, stride=decode_last_stride, padding=padding,
                                              bias=False)

    def _conv_stage(self, cin, cout):
        return nn.Conv2d(cin, cout, 1, stride=1, bias=False)

    def _deconv_stage(self, cout):
        return nn.ConvTranspose2d(cout, cout, 4, stride=2, padding=1, bias=False)

    def forward(self, encode_data):
        ret = {}
        for i, layer in enumerate(self._decode_layers):
            # print(layer,encode_data[layer].size())
            if i > 0:
                deconv = self.deconv_net[i - 1](score)
                # print("deconv from"+self._decode_layers[i-1],deconv.size())
            input_tensor = encode_data[layer]
            score = self.score_net[i](input_tensor)
            # print("conv from"+layer,score.size())
            if i > 0:
                score = deconv + score
        score = self.prehead(score)
        score = self.head(score)
        deconv_final = self.deconv_last(score)
        # print("deconv_final",deconv_final.size())

        return deconv_final