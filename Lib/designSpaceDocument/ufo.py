from __future__ import print_function, division, absolute_import

from ufoLib import fontInfoAttributesVersion1, fontInfoAttributesVersion2, fontInfoAttributesVersion3
from pprint import pprint

"""
    
    A subclassed DesignSpaceDocument that can
        - process the document and generate finished UFOs with MutatorMath.
        - read and write
        - bypass and eventually replace the mutatormath ufo generator.

"""


from designSpaceDocument import DesignSpaceDocument, SourceDescriptor, InstanceDescriptor, AxisDescriptor
from defcon.objects.font import Font
import defcon
from fontMath.mathGlyph import MathGlyph
from fontMath.mathInfo import MathInfo
from fontMath.mathKerning import MathKerning
from mutatorMath.objects.mutator import buildMutator
from mutatorMath.objects.location import biasFromLocations, Location
import os

class DesignSpaceProcessor(DesignSpaceDocument):
    """
        builder of glyphs from designspaces
        validate the data
        if it works, make a generating thing
    """

    fontClass = defcon.Font
    glyphClass = defcon.Glyph
    libClass = defcon.Lib
    glyphContourClass = defcon.Contour
    glyphPointClass = defcon.Point
    glyphComponentClass = defcon.Component
    glyphAnchorClass = defcon.Anchor
    kerningClass = defcon.Kerning
    groupsClass = defcon.Groups
    infoClass = defcon.Info
    featuresClass = defcon.Features

    mathInfoClass = MathInfo
    mathGlyphClass = MathGlyph
    mathKerningClass = MathKerning

    def __init__(self, readerClass=None, writerClass=None, fontClass=None, ufoVersion=2):
        super(DesignSpaceProcessor, self).__init__(readerClass=None, writerClass=None, fontClass=None)
        self.ufoVersion = ufoVersion         # target UFO version
        self.roundGeometry = False
        self._glyphMutators = {}
        self._infoMutator = None
        self._kerningMutator = None
        self.default = None         # name of the default master
        self.defaultLoc = None
        self.fonts = {}
        self.glyphNames = []     # list of all glyphnames

    def generateUFO(self):
        # makes the instances
        self.loadFonts()
        for instanceDescriptor in self.instances:
            if instanceDescriptor.path is None:
                continue
            font = self.makeInstance(instanceDescriptor)
            if not os.path.exists(os.path.dirname(instanceDescriptor.path)):
                os.makedirs(os.path.dirname(instanceDescriptor.path))
            font.save(instanceDescriptor.path, self.ufoVersion)

    def getInfoMutator(self):
        """ Returns a info mutator """
        if self._infoMutator:
            return self._infoMutator
        infoItems = []
        for sourceDescriptor in self.sources:
            loc = Location(sourceDescriptor.location)
            sourceFont = self.fonts[sourceDescriptor.name]
            infoItems.append((loc, self.mathInfoClass(sourceFont.info)))
        bias, self._infoMutator = buildMutator(infoItems, bias=self.defaultLoc)
        return self._infoMutator

    def getKerningMutator(self):
        """ Return a kerning mutator """
        if self._kerningMutator:
            return self._kerningMutator
        kerningItems = []
        for sourceDescriptor in self.sources:
            loc = Location(sourceDescriptor.location)
            sourceFont = self.fonts[sourceDescriptor.name]
            kerningItems.append((loc, self.mathKerningClass(sourceFont.kerning, sourceFont.groups)))
        bias, self._kerningMutator = buildMutator(kerningItems, bias=self.defaultLoc)
        return self._kerningMutator

    def getGlyphMutator(self, glyphName):
        """ Return a glyph mutator """
        if glyphName in self._glyphMutators:
            return self._glyphMutators[glyphName]
        items = []
        for sourceDescriptor in self.sources:
            loc = Location(sourceDescriptor.location)
            f = self.fonts[sourceDescriptor.name]
            if glyphName in sourceDescriptor.mutedGlyphNames:
                continue
            items.append((loc, self.mathGlyphClass(f[glyphName])))
        bias, self._glyphMutators[glyphName] = buildMutator(items, bias=self.defaultLoc)
        return self._glyphMutators[glyphName]

    def loadFonts(self):
        # Load the fonts and find the default candidate based on the info flag
        defaultCandidate = None
        for sourceDescriptor in self.sources:
            names = set()
            if not sourceDescriptor.name in self.fonts:
                self.fonts[sourceDescriptor.name] = self._instantiateFont(sourceDescriptor.path)
                names = names | set(self.fonts[sourceDescriptor.name].keys())
            if sourceDescriptor.copyInfo:
                # we choose you!
                defaultCandidate = sourceDescriptor
        self.glyphNames = list(names)
        # find the default based on mutatorMath bias
        masterLocations = [Location(src.location) for src in self.sources]
        mutatorBias = biasFromLocations(masterLocations)
        c = [src for src in self.sources if src.location==mutatorBias]
        if c:
            mutatorDefaultCandidate = c[0]
        else:
            mutatorDefaultCandidate = None
        # what are we going to do?
        if defaultCandidate is not None and mutatorDefaultCandidate.name != defaultCandidate.name:
            # warn if we have a conflict
            print("Note: conflicting default masters:\n\tUsing %s as default\n\tMutator found %s"%(defaultCandidate.name, mutatorDefaultCandidate.name))
        if defaultCandidate is None and mutatorDefaultCandidate is not None:
            # we didn't have a flag, use the one selected by mutator
            defaultCandidate = mutatorDefaultCandidate
        self.default = defaultCandidate
        self.defaultLoc = Location(self.default.location)

    def makeInstance(self, instanceDescriptor):
        """ Generate a font object for this instance """
        font = self._instantiateFont(None)
        # make fonty things here
        loc = Location(instanceDescriptor.location)
        # make the kerning
        if instanceDescriptor.kerning:
            self.getKerningMutator().makeInstance(loc).extractKerning(font)
        # make the info
        if instanceDescriptor.info:
            self.getInfoMutator().makeInstance(loc).extractInfo(font.info)
            info = self._infoMutator.makeInstance(loc)
            info.extractInfo(font.info)
            font.info.familyName = instanceDescriptor.familyName
            font.info.styleName = instanceDescriptor.styleName
            font.info.postScriptFontName = instanceDescriptor.postScriptFontName
            font.info.styleMapFamilyName = instanceDescriptor.styleMapFamilyName
            font.info.styleMapStyleName = instanceDescriptor.styleMapStyleName
        # copied info
        for sourceDescriptor in self.sources:
            if sourceDescriptor.copyInfo:
                # this is the source
                self._copyFontInfo(self.fonts[sourceDescriptor.name].info, font.info)
            if sourceDescriptor.copyLib:
                font.lib.update(self.fonts[sourceDescriptor.name].lib)
            if sourceDescriptor.copyFeatures:
                featuresText = self.fonts[sourceDescriptor.name].features.text
                if isinstance(featuresText, str):
                    font.features.text = u""+featuresText
                elif isinstance(featuresText, unicode):
                    font.features.text = featuresText
        # glyphs
        for glyphName in self.glyphNames:
            glyphMutator = self.getGlyphMutator(glyphName)
            if glyphName in instanceDescriptor.glyphs.keys():
                # reminder: this is what the glyphData can look like
                # {'instanceLocation': {'custom': 0.0, 'weight': 824.0},
                #  'masters': [{'font': 'master.Adobe VF Prototype.Master_0.0',
                #               'glyphName': 'dollar.nostroke',
                #               'location': {'custom': 0.0, 'weight': 0.0}},
                #              {'font': 'master.Adobe VF Prototype.Master_1.1',
                #               'glyphName': 'dollar.nostroke',
                #               'location': {'custom': 0.0, 'weight': 368.0}},
                #              {'font': 'master.Adobe VF Prototype.Master_2.2',
                #               'glyphName': 'dollar.nostroke',
                #               'location': {'custom': 0.0, 'weight': 1000.0}},
                #              {'font': 'master.Adobe VF Prototype.Master_3.3',
                #               'glyphName': 'dollar.nostroke',
                #               'location': {'custom': 100.0, 'weight': 1000.0}},
                #              {'font': 'master.Adobe VF Prototype.Master_0.4',
                #               'glyphName': 'dollar.nostroke',
                #               'location': {'custom': 100.0, 'weight': 0.0}},
                #              {'font': 'master.Adobe VF Prototype.Master_4.5',
                #               'glyphName': 'dollar.nostroke',
                #               'location': {'custom': 100.0, 'weight': 368.0}}],
                #  'unicodeValue': 36}
                glyphData = instanceDescriptor.glyphs[glyphName]
            else:
                glyphData = {}
            font.newGlyph(glyphName)
            font[glyphName].clear()
            if glyphData.get('mute', False):
                # mute this glyph, skip
                continue
            glyphInstanceLocation = Location(glyphData.get("instanceLocation", instanceDescriptor.location))
            glyphInstanceUnicode = glyphData.get("unicodeValue", font[glyphName].unicode)
            note = glyphData.get("note")
            if note:
                font[glyphName] = note
            masters = glyphData.get("masters", None)
            if masters:
                items = []
                for glyphMaster in masters:
                    sourceGlyphFont = glyphMaster.get("font")
                    sourceGlyphName = glyphMaster.get("glyphName", glyphName)
                    sourceGlyph = MathGlyph(self.fonts.get(sourceGlyphFont)[sourceGlyphName])
                    sourceGlyphLocation = Location(glyphMaster.get("location"))
                    items.append((sourceGlyphLocation, sourceGlyph))
                bias, glyphMutator = buildMutator(items, bias=self.defaultLoc)
            glyphInstanceObject = glyphMutator.makeInstance(glyphInstanceLocation)
            font.newGlyph(glyphName)
            font[glyphName].clear()
            if self.roundGeometry:
                try:
                    glyphInstanceObject = glyphInstanceObject.round()
                except AttributeError:
                    pass
            try:
                glyphInstanceObject.extractGlyph(font[glyphName], onlyGeometry=True)
            except TypeError:
                # this causes ruled glyphs to end up in the wrong glyphname
                # but defcon2 objects don't support it
                pPen = font[glyphName].getPointPen()
                font[glyphName].clear()
                glyphInstanceObject.drawPoints(pPen)
            font[glyphName].width = glyphInstanceObject.width
        return font

    def _instantiateFont(self, path):
        """ Return a instance of a font object with all the given subclasses"""
        return self.fontClass(path,
            libClass=self.libClass,
            kerningClass=self.kerningClass,
            groupsClass=self.groupsClass,
            infoClass=self.infoClass,
            featuresClass=self.featuresClass,
            glyphClass=self.glyphClass,
            glyphContourClass=self.glyphContourClass,
            glyphPointClass=self.glyphPointClass,
            glyphComponentClass=self.glyphComponentClass,
            glyphAnchorClass=self.glyphAnchorClass)

    def _copyFontInfo(self, sourceInfo, targetInfo):
        """ Copy the non-calculating fields from the source info."""
        infoAttributes = [
            "versionMajor",
            "versionMinor",
            "copyright",
            "trademark",
            "note",
            "openTypeGaspRangeRecords",
            "openTypeHeadCreated",
            "openTypeHeadFlags",
            "openTypeNameDesigner",
            "openTypeNameDesignerURL",
            "openTypeNameManufacturer",
            "openTypeNameManufacturerURL",
            "openTypeNameLicense",
            "openTypeNameLicenseURL",
            "openTypeNameVersion",
            "openTypeNameUniqueID",
            "openTypeNameDescription",
            "#openTypeNamePreferredFamilyName",
            "#openTypeNamePreferredSubfamilyName",
            "#openTypeNameCompatibleFullName",
            "openTypeNameSampleText",
            "openTypeNameWWSFamilyName",
            "openTypeNameWWSSubfamilyName",
            "openTypeNameRecords",
            "openTypeOS2Selection",
            "openTypeOS2VendorID",
            "openTypeOS2Panose",
            "openTypeOS2FamilyClass",
            "openTypeOS2UnicodeRanges",
            "openTypeOS2CodePageRanges",
            "openTypeOS2Type",
            "postscriptIsFixedPitch",
            "postscriptForceBold",
            "postscriptDefaultCharacter",
            "postscriptWindowsCharacterSet"
        ]
        for infoAttribute in infoAttributes:
            copy = False
            if self.ufoVersion == 1 and infoAttribute in fontInfoAttributesVersion1:
                copy = True
            elif self.ufoVersion == 2 and infoAttribute in fontInfoAttributesVersion2:
                copy = True
            elif self.ufoVersion == 3 and infoAttribute in fontInfoAttributesVersion3:
                copy = True
            if copy:
                value = getattr(sourceInfo, infoAttribute)
                setattr(targetInfo, infoAttribute, value)


if __name__ == "__main__":
    # standalone test
    import shutil

    def addGlyphs(font, s):
        # we need to add the glyphs
        for n in ['glyphOne', 'glyphTwo', 'glyphThree', 'glyphFour']:
            font.newGlyph(n)
            g = font[n]
            p = g.getPen()
            p.moveTo((0,0))
            p.lineTo((s,0))
            p.lineTo((s,s))
            p.lineTo((0,s))
            p.closePath()
            g.move((0,s*2))
            g.width = s

    def fillInfo(font):
        font.info.unitsPerEm = 1000
        font.info.ascender = 800
        font.info.descender = -200

    def makeTestFonts(rootPath):
        """ Make some test fonts that have the kerning problem."""
        path1 = os.path.join(rootPath, "geometryMaster1.ufo")
        path2 = os.path.join(rootPath, "geometryMaster2.ufo")
        path3 = os.path.join(rootPath, "my_test_instance_dir_one", "geometryInstance%3.3f.ufo")
        path4 = os.path.join(rootPath, "my_test_instance_dir_two", "geometryInstanceAnisotropic1.ufo")
        path5 = os.path.join(rootPath, "my_test_instance_dir_two", "geometryInstanceAnisotropic2.ufo")

        # Two masters
        f1 = Font()
        addGlyphs(f1, 100)
        f1.features.text = u"# features text from master 1"

        f2 = Font()
        addGlyphs(f2, 500)
        f2.features.text = u"# features text from master 2"


        fillInfo(f1)
        f1.info.ascender = 400
        f1.info.descender = -200
        fillInfo(f2)
        f2.info.ascender = 600
        f2.info.descender = -100

        f1.info.copyright = u"This is the copyright notice from master 1"
        f2.info.copyright = u"This is the copyright notice from master 2"

        # save
        f1.save(path1, 2)
        f2.save(path2, 2)
        return path1, path2, path3, path4, path5

    def test0(docPath):
        # make the test fonts and a test document
        testFontPath = os.path.join(os.getcwd(), "automatic_testfonts")
        m1, m2, i1, i2, i3 = makeTestFonts(testFontPath)
        d = DesignSpaceProcessor()
        a = AxisDescriptor()
        a.name = "pop"
        a.minimum = 50
        a.maximum = 1000
        a.default = 0
        a.tag = "pop*"
        d.addAxis(a)
        
        s1 = SourceDescriptor()
        s1.path = m1
        s1.location = dict(pop=a.minimum)
        s1.name = "test.master.1"
        s1.copyInfo = True
        s1.copyFeatures = True
        d.addSource(s1)

        s2 = SourceDescriptor()
        s2.path = m2
        s2.location = dict(pop=1000)
        s2.name = "test.master.2"
        #s2.copyInfo = True
        d.addSource(s2)

        for counter in range(3):
            factor = counter / 2        
            i = InstanceDescriptor()
            v = a.minimum+factor*(a.maximum-a.minimum)
            i.path = i1%v
            i.familyName = "TestFamily"
            i.styleName = "TestStyle_pop%3.3f"%(v)
            i.name = "%s-%s"%(i.familyName, i.styleName)
            i.location = dict(pop=v)
            i.info = True
            i.kerning = True
            if counter == 2:
                i.glyphs['glyphTwo'] = dict(name="glyphTwo", mute=True)
            d.addInstance(i)
        d.write(docPath)

    def test1(docPath):
        # execute the test document
        d = DesignSpaceProcessor()
        d.read(docPath)
        d.generateUFO()

    selfTest = True
    if selfTest:
        testRoot = os.path.join(os.getcwd(), "automatic_testfonts")
        if os.path.exists(testRoot):
            shutil.rmtree(testRoot)
        docPath = os.path.join(testRoot, "automatic_test.designspace")
        test0(docPath)
        test1(docPath)
